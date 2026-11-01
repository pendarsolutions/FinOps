"""Monitored servers. Read-only towards the servers: nothing here can change anything on one."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleet import enroll_command, removal_command, suggest_plans
from pricing_engine import CatalogSnapshot
from shared_types import ResourceDraft

from ..config import get_settings
from ..db import get_db
from ..fleet_service import collect_one, fleet_key, org_settings_of, server_costs, to_resource
from ..orm import Server
from ..security import Principal, audit, current_principal, require
from ..services import create_inventory, snapshot

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]*$")


class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        if not HOST_RE.match(v):
            raise ValueError("host must be an IP address or a hostname")
        return v


class ServerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    environment: Literal["production", "staging", "development", "test"] | None = None
    provider_id: str | None = None
    sku: str | None = None
    resource_class: str | None = None
    storage_type: str | None = None
    download_gb_override: Decimal | None = Field(default=None, ge=0)
    upload_gb_override: Decimal | None = Field(default=None, ge=0)
    renewal_date: date | None = None


def _get(db: Session, p: Principal, server_id: str) -> Server:
    server = db.get(Server, server_id)
    if server is None or server.organization_id != p.org.id:
        raise HTTPException(404, "server not found")
    return server


def _view(server: Server, costs: dict[str, Any]) -> dict[str, Any]:
    return {"id": server.id, "name": server.name, "host": server.host, "port": server.port, "status": server.status,
            "last_seen_at": server.last_seen_at, "last_error": server.last_error, "hostname": server.hostname,
            "os": server.os, "cpu_cores": server.cpu_cores, "mem_total_kb": server.mem_total_kb,
            "disk_total_kb": server.disk_total_kb, "usage": server.usage or {}, "environment": server.environment,
            "provider_id": server.provider_id, "sku": server.sku, "resource_class": server.resource_class,
            "storage_type": server.storage_type, "download_gb_override": server.download_gb_override,
            "upload_gb_override": server.upload_gb_override, "renewal_date": server.renewal_date,
            "priced": costs["priced"], "cost_status": costs["status"], "monthly_total_toman": costs["monthly_total_toman"],
            "avoidable_monthly_toman": costs["avoidable_monthly_toman"]}


def _suggestions(server: Server, snap: CatalogSnapshot) -> list[dict[str, Any]]:
    plans = suggest_plans(server.cpu_cores, server.mem_total_kb, server.disk_total_kb, snap.items)
    return [{"provider_id": i.provider_id, "sku": i.sku, "name": i.name, "price_toman": i.price_toman,
             "cpu_cores": i.cpu_cores, "ram_gb": i.ram_gb, "storage_gb": i.storage_gb, "datacenter": i.datacenter}
            for i in plans]


@router.get("")
def list_servers(db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    servers = list(db.scalars(select(Server).where(Server.organization_id == p.org.id).order_by(Server.name)))
    snap = snapshot(db)
    org = org_settings_of(db, p.org.id)
    views = [_view(s, server_costs(s, snap, org)) for s in servers]
    exact = [v for v in views if v["cost_status"] == "EXACT"]
    return {
        "servers": views,
        "summary": {
            "total": len(views), "online": sum(v["status"] == "online" for v in views),
            "exact_priced": len(exact), "not_priced": len(views) - len(exact),
            "monthly_total_toman": sum((v["monthly_total_toman"] for v in exact), Decimal(0)),
            "avoidable_monthly_toman": sum((v["avoidable_monthly_toman"] or Decimal(0) for v in exact), Decimal(0)),
        },
    }


@router.get("/enroll-command")
def get_enroll_command(db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    key = fleet_key(db, p.org.id)
    db.commit()
    return {"command": enroll_command(key.public_key, get_settings().collector_source_ip), "public_key": key.public_key,
            "removal_command": removal_command()}


@router.post("")
def add_server(body: ServerIn, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    exists = db.scalar(select(Server).where(Server.organization_id == p.org.id, Server.host == body.host,
                                            Server.port == body.port))
    if exists:
        raise HTTPException(409, "this server is already added")
    server = Server(organization_id=p.org.id, name=body.name, host=body.host, port=body.port, usage={})
    db.add(server)
    db.flush()
    audit(db, p, "server.add", "server", server.id, {"host": body.host, "port": body.port})
    db.commit()
    collect_one(db, server)
    return _view(server, server_costs(server, snapshot(db), org_settings_of(db, p.org.id)))


@router.post("/inventory")
def to_inventory(db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    """Start a normal inventory from the servers, for comparison and reports. It still needs confirming."""
    snap = snapshot(db)
    drafts = []
    for server in db.scalars(select(Server).where(Server.organization_id == p.org.id, Server.provider_id.is_not(None))
                             .order_by(Server.name)):
        r = to_resource(server, snap)
        drafts.append(ResourceDraft(
            name=server.name, external_ref=server.host, environment=server.environment, provider_id=server.provider_id,
            sku=server.sku, resource_class=server.resource_class, quantity=Decimal(1), cpu_cores=r.cpu_cores, ram_gb=r.ram_gb,
            storage_gb=r.storage_gb, storage_type=server.storage_type,
            expected_monthly_download_gb=r.expected_monthly_download_gb,
            expected_monthly_upload_gb=r.expected_monthly_upload_gb, requires_public_ipv4=True, billing_mode="monthly",
            metrics=r.metrics.model_dump(mode="json") if r.metrics else None))
    if not drafts:
        raise HTTPException(409, "confirm the provider of at least one server first")
    inv = create_inventory(db, p, "Servers", "servers", drafts, {"origin": "monitored servers"})
    return {"id": inv.id}


@router.get("/{server_id}")
def get_server(server_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    server = _get(db, p, server_id)
    snap = snapshot(db)
    costs = server_costs(server, snap, org_settings_of(db, p.org.id))
    return {**_view(server, costs), "breakdown": costs["breakdown"], "recommendations": costs["recommendations"],
            "suggestions": _suggestions(server, snap)}


@router.patch("/{server_id}")
def patch_server(server_id: str, body: ServerPatch, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    server = _get(db, p, server_id)
    updates = body.model_dump(exclude_unset=True)
    provider, sku = updates.get("provider_id", server.provider_id), updates.get("sku", server.sku)
    snap = snapshot(db)
    if provider is not None and snap.provider_policy(provider) is None:
        raise HTTPException(422, "unknown provider")
    if provider is not None and sku is not None and not snap.find(provider, sku=sku):
        raise HTTPException(422, "this plan isn't in the provider's catalog")
    for field, value in updates.items():
        setattr(server, field, value)
    audit(db, p, "server.update", "server", server.id, {k: str(v) for k, v in updates.items()})
    db.commit()
    return _view(server, server_costs(server, snap, org_settings_of(db, p.org.id)))


@router.post("/{server_id}/check")
def check_server(server_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    server = _get(db, p, server_id)
    collect_one(db, server)
    return _view(server, server_costs(server, snapshot(db), org_settings_of(db, p.org.id)))


@router.post("/{server_id}/trust-new-identity")
def trust_new_identity(server_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    """After a legitimate reinstall. Audited, because it is also what an attacker would want."""
    server = _get(db, p, server_id)
    server.host_key = None
    audit(db, p, "server.trust_new_identity", "server", server.id)
    db.commit()
    collect_one(db, server)
    return _view(server, server_costs(server, snapshot(db), org_settings_of(db, p.org.id)))


@router.delete("/{server_id}")
def delete_server(server_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    server = _get(db, p, server_id)
    db.delete(server)
    audit(db, p, "server.delete", "server", server_id, {"host": server.host})
    db.commit()
    return {"deleted": server_id, "removal_command": removal_command()}
