"""Operational CLI: `python -m finops_api.cli <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from .catalog_store import run_provider_sync, seed_pricing
from .config import get_settings
from .db import Base, SessionLocal, get_engine
from .orm import ProviderRow, Upload, User
from .security import create_user_with_org


def cmd_migrate(_: argparse.Namespace) -> None:
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")
    print("migrations applied")


def cmd_create_all(_: argparse.Namespace) -> None:
    """Dev/test shortcut for SQLite. Postgres environments use `migrate`."""
    import finops_api.orm  # noqa: F401

    Base.metadata.create_all(get_engine())
    print("tables created")


def cmd_seed_pricing(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        stats = seed_pricing(db, get_settings().seed_dir)
    print(json.dumps(stats))


def cmd_seed_demo_user(args: argparse.Namespace) -> None:
    s = get_settings()
    if s.is_prod:
        sys.exit("refusing to create the demo user in staging/prod")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email)):
            print(f"demo user {args.email} already exists")
            return
        create_user_with_org(db, args.email, args.password, "Demo", "Demo workspace")
        db.commit()
    print(f"created {args.email}")


def cmd_sync(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        ids = [args.provider] if args.provider else [p.id for p in db.scalars(select(ProviderRow))]
        failed = False
        for pid in ids:
            run = run_provider_sync(db, pid, triggered_by="cli")
            print(json.dumps({"provider": pid, "status": run.status, "seen": run.items_seen,
                              "changed": run.items_changed, "warnings": run.warnings, "error": run.error},
                             ensure_ascii=False))
            failed |= run.status in ("failed", "quarantined")
    if failed and args.strict:
        sys.exit(1)


def cmd_purge_uploads(_: argparse.Namespace) -> None:
    now = datetime.now(UTC)
    n = 0
    with SessionLocal() as db:
        for up in db.scalars(select(Upload).where(Upload.deleted_at.is_(None))):
            due = up.delete_after if up.delete_after.tzinfo else up.delete_after.replace(tzinfo=UTC)
            if due <= now:
                if up.storage_path:
                    Path(up.storage_path).unlink(missing_ok=True)
                up.storage_path, up.deleted_at = None, now
                n += 1
        db.commit()
    print(f"purged {n} raw invoice file(s)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="finops")
    sub = ap.add_subparsers(required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    sub.add_parser("create-all").set_defaults(fn=cmd_create_all)
    sub.add_parser("seed-pricing").set_defaults(fn=cmd_seed_pricing)
    d = sub.add_parser("seed-demo-user")
    d.add_argument("--email", default="demo@finops-agent.local")
    d.add_argument("--password", default="demo-password-1")
    d.set_defaults(fn=cmd_seed_demo_user)
    s = sub.add_parser("sync-prices")
    s.add_argument("--provider")
    s.add_argument("--strict", action="store_true", help="exit 1 if any sync failed or was quarantined")
    s.set_defaults(fn=cmd_sync)
    sub.add_parser("purge-uploads").set_defaults(fn=cmd_purge_uploads)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
