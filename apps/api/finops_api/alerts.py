"""Outgoing notifications: email and Bale. Best effort: a failed notification is logged and never
breaks the job that raised it. With nothing configured, messages only go to the structured log."""

from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .orm import PriceSyncRun

log = logging.getLogger("finops.alerts")

BALE_API = "https://tapi.bale.ai"
#: how many individual price changes one message lists
MAX_LISTED_CHANGES = 10


def _send_email(subject: str, body: str) -> None:
    s = get_settings()
    if not (s.smtp_host and s.alert_email_to):
        return
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, s.alert_email_to
    msg["From"] = s.smtp_from or s.smtp_user or s.alert_email_to
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        smtp.send_message(msg)


def _send_bale(subject: str, body: str) -> None:
    s = get_settings()
    if not (s.bale_bot_token and s.bale_chat_id):
        return
    resp = httpx.post(f"{BALE_API}/bot{s.bale_bot_token}/sendMessage", timeout=15,
                      json={"chat_id": s.bale_chat_id, "text": f"{subject}\n\n{body}"})
    resp.raise_for_status()


def notify(subject: str, body: str) -> None:
    log.warning(json.dumps({"alert": subject, "body": body}, ensure_ascii=False))
    for channel, send in (("email", _send_email), ("bale", _send_bale)):
        try:
            send(subject, body)
        except Exception as exc:  # noqa: BLE001 - never let alerting break a sync; the token must not reach the log
            log.error(json.dumps({"alert_delivery_failed": channel, "error": type(exc).__name__}))


def _previous_status(db: Session, run: PriceSyncRun) -> str | None:
    return db.scalar(select(PriceSyncRun.status).where(PriceSyncRun.provider_id == run.provider_id,
                                                       PriceSyncRun.id != run.id,
                                                       PriceSyncRun.started_at < run.started_at)
                     .order_by(PriceSyncRun.started_at.desc()).limit(1))


def format_price_changes(run: PriceSyncRun) -> str | None:
    """Lines for rows whose price moved. Rows that only appeared or disappeared aren't price changes."""
    moved = [c for c in (run.summary or {}).get("changes", [])
             if c.get("kind") == "changed" and c.get("old_price_toman") != c.get("new_price_toman")]
    if not moved:
        return None
    lines = [f"{c['sku']}: {c['old_price_toman']} -> {c['new_price_toman']} Toman" for c in moved[:MAX_LISTED_CHANGES]]
    if len(moved) > MAX_LISTED_CHANGES:
        lines.append(f"... and {len(moved) - MAX_LISTED_CHANGES} more")
    return "\n".join(lines)


def sync_alert(db: Session, run: PriceSyncRun) -> None:
    """A provider that stays failed alerts once, when it starts failing, rather than on every run."""
    pid = run.provider_id
    if run.status == "quarantined":
        notify(f"Price update needs review: {pid}",
               "Prices moved sharply, so nothing was applied. Approve or ignore it on the Integrations page.\n"
               f"{(run.warnings or [''])[0]}")
    elif run.status == "failed":
        if _previous_status(db, run) != "failed":
            notify(f"Price update failed: {pid}", f"{run.error}\nThe last known prices stay active.")
    elif run.status in ("ok", "warning") and (changes := format_price_changes(run)):
        notify(f"Prices changed: {pid}", changes)
