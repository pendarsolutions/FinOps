"""Celery worker: nightly provider price sync (with guardrails) and invoice retention purge.

Run:  celery -A finops_worker.tasks worker -B --loglevel=INFO
"""

from __future__ import annotations

import json
import logging
import os

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from finops_api.catalog_store import run_provider_sync
from finops_api.db import SessionLocal
from finops_api.orm import ProviderRow
from finops_api.platform import configure_logging

configure_logging()
log = logging.getLogger("finops.worker")

broker = os.environ.get("FINOPS_REDIS_URL", "redis://localhost:6379/0")
app = Celery("finops", broker=broker, backend=broker)
app.conf.update(
    timezone="Asia/Tehran",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "nightly-price-sync": {"task": "finops_worker.tasks.sync_all", "schedule": crontab(hour=3, minute=15)},
        "purge-expired-invoices": {"task": "finops_worker.tasks.purge_uploads", "schedule": crontab(hour=4, minute=0)},
    },
)


def _alert(run) -> None:
    """Sync failures/quarantines are logged at ERROR as structured JSON (ship to your alerting stack);
    they are also visible in the product (Integrations / Price Catalog pages)."""
    if run.status in ("failed", "quarantined"):
        log.error(json.dumps({"alert": "price_sync", "provider": run.provider_id, "status": run.status,
                              "error": run.error, "warnings": run.warnings}, ensure_ascii=False))
    elif run.status == "warning":
        log.warning(json.dumps({"alert": "price_sync_warning", "provider": run.provider_id,
                                "warnings": run.warnings}, ensure_ascii=False))


@app.task(name="finops_worker.tasks.sync_provider", autoretry_for=(ConnectionError,), retry_backoff=True,
          max_retries=3)
def sync_provider(provider_id: str, triggered_by: str = "schedule") -> dict:
    with SessionLocal() as db:
        run = run_provider_sync(db, provider_id, triggered_by=triggered_by)
        _alert(run)
        return {"provider_id": provider_id, "status": run.status, "run_id": run.id}


@app.task(name="finops_worker.tasks.sync_all")
def sync_all() -> list[dict]:
    with SessionLocal() as db:
        ids = [p.id for p in db.scalars(select(ProviderRow))]
    return [sync_provider(pid, "schedule") for pid in ids]


@app.task(name="finops_worker.tasks.purge_uploads")
def purge_uploads() -> None:
    from argparse import Namespace

    from finops_api.cli import cmd_purge_uploads

    cmd_purge_uploads(Namespace())
