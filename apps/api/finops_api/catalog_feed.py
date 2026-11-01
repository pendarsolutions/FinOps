"""Publishing and pulling the signed price catalog."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from provider_adapters import FeedAdapter, FeedError, build_feed, read_feed, sign_feed
from provider_adapters.base import RawCatalog

from .alerts import notify, sync_alert
from .catalog_store import current_versions, row_to_item, run_provider_sync
from .config import get_settings
from .orm import PriceSyncRun, ProviderRow

FEED_FILE = "catalog.json"
TRIGGER = "catalog-feed"
MAX_FEED_BYTES = 20 * 1024 * 1024


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def publish(db: Session, out_dir: Path, signing_key_b64: str, now: datetime | None = None) -> Path:
    content = build_feed([row_to_item(r) for r in current_versions(db)], now or datetime.now(UTC))
    signature = sign_feed(content, signing_key_b64)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(out_dir / FEED_FILE, content)
    _write_atomic(out_dir / f"{FEED_FILE}.sig", signature.encode())
    return out_dir / FEED_FILE


def publish_if_configured(db: Session) -> None:
    s = get_settings()
    if s.catalog_publish_dir and s.catalog_signing_key:
        publish(db, s.catalog_publish_dir, s.catalog_signing_key)


def _last_applied(db: Session, provider_id: str) -> datetime | None:
    run = db.scalar(select(PriceSyncRun).where(PriceSyncRun.provider_id == provider_id, PriceSyncRun.triggered_by == TRIGGER,
                                               PriceSyncRun.status != "failed")
                    .order_by(PriceSyncRun.started_at.desc()).limit(1))
    stamp = (run.summary or {}).get("feed_generated_at") if run else None
    return datetime.fromisoformat(stamp) if stamp else None


def apply_feed(db: Session, content: bytes, signature: str, public_key: str) -> dict[str, str]:
    """Verified rows go through the normal guardrails, per provider. An older feed is ignored, so nobody can roll
    prices back by replaying a validly signed old file."""
    generated_at, by_provider = read_feed(content, signature, public_key)
    now = datetime.now(UTC)
    known = {p.id for p in db.scalars(select(ProviderRow))}
    out: dict[str, str] = {}
    for provider_id, rows in sorted(by_provider.items()):
        if provider_id not in known:
            out[provider_id] = "skipped_unknown_provider"
            continue
        last = _last_applied(db, provider_id)
        if last is not None and generated_at <= last:
            out[provider_id] = "skipped_not_newer"
            continue
        current = [row_to_item(r) for r in current_versions(db, provider_id)]
        raw = RawCatalog(provider_id, TRIGGER, now, json.dumps(rows, sort_keys=True, ensure_ascii=False),
                         content_type="application/json")
        run = run_provider_sync(db, provider_id, triggered_by=TRIGGER, raw=raw, adapter=FeedAdapter(provider_id, current, rows))
        run.summary = {**(run.summary or {}), "feed_generated_at": generated_at.isoformat()}
        db.commit()
        sync_alert(db, run)
        out[provider_id] = run.status
    return out


def pull(db: Session) -> dict[str, str]:
    s = get_settings()
    if not s.catalog_public_key:
        raise FeedError("FINOPS_CATALOG_URL is set without FINOPS_CATALOG_PUBLIC_KEY; refusing unverified prices")
    base = s.catalog_url.rstrip("/")
    try:
        content_resp = httpx.get(f"{base}/{FEED_FILE}", timeout=60, follow_redirects=True)
        content_resp.raise_for_status()
        sig_resp = httpx.get(f"{base}/{FEED_FILE}.sig", timeout=30, follow_redirects=True)
        sig_resp.raise_for_status()
        if len(content_resp.content) > MAX_FEED_BYTES:
            raise FeedError("catalog file is too large")
        return apply_feed(db, content_resp.content, sig_resp.text.strip(), s.catalog_public_key)
    except (httpx.HTTPError, FeedError) as exc:
        notify("Price catalog download failed", f"{base}: {exc}. The last known prices stay active.")
        raise
