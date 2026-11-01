"""Monitored servers: collecting usage and pricing it with the same deterministic engine as everything else."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fleet import (
    Collected,
    CollectError,
    HostKeyChanged,
    Sample,
    SshError,
    collect,
    generate_keypair,
    parse_collect,
    summarize,
)
from pricing_engine import CatalogSnapshot, Resource, UsageMetrics, price_resource
from recommendation_engine import OrgSettings, recommend
from recommendation_engine import summarize as summarize_recs

from .orm import FleetKey, Organization, Server, ServerSample
from .platform import decrypt_secret, encrypt_secret

USAGE_WINDOW_DAYS = 30
SAMPLE_RETENTION_DAYS = 90
RENEWAL_ALERT_DAYS = (7, 3, 1)
KIB_PER_GIB = Decimal(1024 ** 2)
MAX_PARALLEL_COLLECTS = 16


def fleet_key(db: Session, organization_id: str) -> FleetKey:
    key = db.get(FleetKey, organization_id)
    if key is None:
        private, public = generate_keypair()
        key = FleetKey(organization_id=organization_id, public_key=public, private_key_encrypted=encrypt_secret(private))
        db.add(key)
        db.flush()
    return key


def _as_sample(row: ServerSample) -> Sample:
    taken = row.taken_at if row.taken_at.tzinfo else row.taken_at.replace(tzinfo=UTC)
    return Sample(taken_at=taken, cpu_total=row.cpu_total, cpu_idle=row.cpu_idle, mem_total_kb=row.mem_total_kb,
                  mem_available_kb=row.mem_available_kb, disk_total_kb=row.disk_total_kb, disk_used_kb=row.disk_used_kb,
                  rx_bytes=row.rx_bytes, tx_bytes=row.tx_bytes)


def refresh_usage(db: Session, server: Server, at: datetime) -> None:
    rows = db.scalars(select(ServerSample).where(ServerSample.server_id == server.id,
                                                 ServerSample.taken_at >= at - timedelta(days=USAGE_WINDOW_DAYS)))
    server.usage = summarize([_as_sample(r) for r in rows], USAGE_WINDOW_DAYS).as_json()


def record_collection(db: Session, server: Server, parsed: Collected, host_key: str) -> None:
    s = parsed.sample
    db.add(ServerSample(server_id=server.id, taken_at=s.taken_at, cpu_total=s.cpu_total, cpu_idle=s.cpu_idle,
                        mem_total_kb=s.mem_total_kb, mem_available_kb=s.mem_available_kb, disk_total_kb=s.disk_total_kb,
                        disk_used_kb=s.disk_used_kb, rx_bytes=s.rx_bytes, tx_bytes=s.tx_bytes))
    db.flush()
    server.status, server.last_error, server.last_seen_at = "online", None, s.taken_at
    server.host_key = server.host_key or host_key
    server.hostname, server.os, server.cpu_cores = parsed.hostname, parsed.os, parsed.cpu_cores
    server.mem_total_kb, server.disk_total_kb = s.mem_total_kb, s.disk_total_kb
    refresh_usage(db, server, s.taken_at)


def _fetch(host: str, port: int, private_key: str, known: str | None) -> tuple[str, Any]:
    try:
        result = collect(host, port, private_key, known)
        return "ok", (parse_collect(result.output, datetime.now(UTC)), result.host_key)
    except HostKeyChanged as exc:
        return "host_key_changed", str(exc)
    except (SshError, CollectError) as exc:
        return "unreachable", str(exc)


def _apply(db: Session, server: Server, outcome: tuple[str, Any]) -> None:
    state, value = outcome
    if state == "ok":
        record_collection(db, server, value[0], value[1])
    else:
        server.status, server.last_error = state, value


def collect_one(db: Session, server: Server) -> None:
    key = fleet_key(db, server.organization_id)
    _apply(db, server, _fetch(server.host, server.port, decrypt_secret(key.private_key_encrypted), server.host_key))
    db.commit()


def collect_all(db: Session) -> dict[str, int]:
    """Network first and in parallel, one slow server can't hold up the rest; database writes after."""
    servers = list(db.scalars(select(Server)))
    keys = {s.organization_id: decrypt_secret(fleet_key(db, s.organization_id).private_key_encrypted) for s in servers}
    with ThreadPoolExecutor(MAX_PARALLEL_COLLECTS) as pool:
        outcomes = list(pool.map(lambda s: _fetch(s[0], s[1], s[2], s[3]),
                                 [(s.host, s.port, keys[s.organization_id], s.host_key) for s in servers]))
    counts: dict[str, int] = {}
    for server, outcome in zip(servers, outcomes, strict=True):
        _apply(db, server, outcome)
        counts[server.status] = counts.get(server.status, 0) + 1
    db.commit()
    return counts


def purge_samples(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=SAMPLE_RETENTION_DAYS)
    result = db.execute(delete(ServerSample).where(ServerSample.taken_at < cutoff))
    db.commit()
    return result.rowcount or 0


def _ceil(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def to_resource(server: Server, snapshot: CatalogSnapshot) -> Resource | None:
    """None until the user has said which provider this server is with."""
    if not server.provider_id:
        return None
    usage = server.usage or {}
    plan = next(iter(snapshot.find(server.provider_id, sku=server.sku)), None) if server.sku else None
    # a plan's own specs are exact; what a server reports is lower because of kernel and filesystem overhead
    cpu = plan.cpu_cores if plan and plan.cpu_cores is not None else _dec(server.cpu_cores)
    ram = plan.ram_gb if plan and plan.ram_gb is not None else (
        _ceil(Decimal(server.mem_total_kb) / KIB_PER_GIB) if server.mem_total_kb else None)
    disk = None if plan else (_ceil(Decimal(server.disk_total_kb) / KIB_PER_GIB) if server.disk_total_kb else None)
    metrics = None
    if usage.get("p95_cpu_percent") is not None or usage.get("p95_ram_percent") is not None:
        metrics = UsageMetrics(p95_cpu_percent=usage.get("p95_cpu_percent"), p95_ram_percent=usage.get("p95_ram_percent"),
                               disk_used_gb=usage.get("disk_used_gb"), observation_days=usage.get("observation_days"),
                               source="server collector")
    download = server.download_gb_override if server.download_gb_override is not None else usage.get("monthly_download_gb")
    upload = server.upload_gb_override if server.upload_gb_override is not None else usage.get("monthly_upload_gb")
    return Resource(id=server.id, name=server.name, provider_id=server.provider_id, service_type="compute_vm",
                    sku=server.sku, resource_class=server.resource_class, environment=server.environment,
                    cpu_cores=cpu, ram_gb=ram, storage_gb=disk, storage_type=server.storage_type,
                    expected_monthly_download_gb=download, expected_monthly_upload_gb=upload,
                    requires_public_ipv4=True, metrics=metrics)


def traffic_assumption(server: Server) -> str | None:
    usage = server.usage or {}
    if server.download_gb_override is not None or server.upload_gb_override is not None:
        return "Traffic is the figure you entered, not a measurement."
    if usage.get("traffic_projected") and usage.get("monthly_download_gb") is not None:
        return ("Monthly traffic is projected from the time this server has been observed. Download means traffic "
                "leaving the server.")
    return None


def server_costs(server: Server, snapshot: CatalogSnapshot, org: OrgSettings) -> dict[str, Any]:
    resource = to_resource(server, snapshot)
    if resource is None:
        return {"priced": False, "status": "NOT_CONFIRMED", "monthly_total_toman": None, "avoidable_monthly_toman": None,
                "breakdown": None, "recommendations": []}
    breakdown = price_resource(resource, snapshot)
    recs = recommend([resource], snapshot, None, org)
    summary = summarize_recs(recs, breakdown.monthly_total_toman, snapshot)
    data = breakdown.model_dump(mode="json")
    if note := traffic_assumption(server):
        data["assumptions"] = [note, *data["assumptions"]]
    return {"priced": True, "status": breakdown.status.value, "monthly_total_toman": breakdown.monthly_total_toman,
            "avoidable_monthly_toman": summary["avoidable_monthly_toman"], "breakdown": data,
            "recommendations": [r.model_dump(mode="json") for r in recs]}


def renewals_due(db: Session, today: date) -> list[tuple[Server, int]]:
    days = {today + timedelta(days=d): d for d in RENEWAL_ALERT_DAYS}
    rows = db.scalars(select(Server).where(Server.renewal_date.in_(days)))
    return [(s, days[s.renewal_date]) for s in rows]


def org_settings_of(db: Session, organization_id: str) -> OrgSettings:
    org = db.get(Organization, organization_id)
    return OrgSettings(engineer_day_rate_toman=(org.settings or {}).get("engineer_day_rate_toman"))
