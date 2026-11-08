"""Operational CLI: `python -m finops_api.cli <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from .alerts import sync_alert
from .catalog_store import import_manual_prices, run_provider_sync, seed_pricing
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


def cmd_reset_password(args: argparse.Namespace) -> None:
    """For when nobody can sign in: sets a new password and ends that person's sessions."""
    import secrets

    from .orm import AuditLog
    from .security import set_password

    email = args.email.lower().strip()
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else secrets.token_urlsafe(12)
    if len(password) < 10:
        sys.exit("the password needs at least 10 characters")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"no account uses {email}")
        set_password(user, password)
        db.add(AuditLog(user_id=user.id, action="auth.password_reset_cli", entity_type="user", entity_id=user.id,
                        detail={}))
        db.commit()
    if args.password_stdin:
        print(f"password changed for {email}; their other sessions have ended")
    else:
        print(f"new password for {email}: {password}\nthey can change it under Settings after signing in")


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


def cmd_price_import(args: argparse.Namespace) -> None:
    content = Path(args.file).read_text(encoding="utf-8")
    with SessionLocal() as db:
        run = import_manual_prices(db, args.provider, content, triggered_by="manual-file")
        sync_alert(db, run)
        print(json.dumps({"provider": args.provider, "status": run.status, "changed": run.items_changed,
                          "warnings": run.warnings, "error": run.error}, ensure_ascii=False))
    if run.status == "failed":
        sys.exit(1)


def cmd_catalog_keygen(_: argparse.Namespace) -> None:
    from provider_adapters import generate_signing_key

    private, public = generate_signing_key()
    print(f"FINOPS_CATALOG_SIGNING_KEY={private}   # publisher only; keep this secret")
    print(f"FINOPS_CATALOG_PUBLIC_KEY={public}")


def cmd_catalog_publish(args: argparse.Namespace) -> None:
    from .catalog_feed import publish

    s = get_settings()
    out = Path(args.out) if args.out else s.catalog_publish_dir
    if not out or not s.catalog_signing_key:
        sys.exit("needs FINOPS_CATALOG_SIGNING_KEY and --out (or FINOPS_CATALOG_PUBLISH_DIR)")
    with SessionLocal() as db:
        print(publish(db, out, s.catalog_signing_key))


def cmd_catalog_pull(_: argparse.Namespace) -> None:
    from .catalog_feed import pull

    if not get_settings().catalog_url:
        sys.exit("FINOPS_CATALOG_URL is not set")
    with SessionLocal() as db:
        print(json.dumps(pull(db)))


def cmd_collect_servers(_: argparse.Namespace) -> None:
    from .fleet_service import collect_all

    with SessionLocal() as db:
        print(json.dumps(collect_all(db)))


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
    rp = sub.add_parser("reset-password", help="set a new password for an account (prints a generated one)")
    rp.add_argument("--email", required=True)
    rp.add_argument("--password-stdin", action="store_true", help="read the new password from standard input")
    rp.set_defaults(fn=cmd_reset_password)
    s = sub.add_parser("sync-prices")
    s.add_argument("--provider")
    s.add_argument("--strict", action="store_true", help="exit 1 if any sync failed or was quarantined")
    s.set_defaults(fn=cmd_sync)
    m = sub.add_parser("price-import", help="apply a reviewed price file (see docs/provider-adapters.md)")
    m.add_argument("--provider", required=True)
    m.add_argument("--file", required=True)
    m.set_defaults(fn=cmd_price_import)
    sub.add_parser("collect-servers").set_defaults(fn=cmd_collect_servers)
    sub.add_parser("catalog-keygen").set_defaults(fn=cmd_catalog_keygen)
    cp = sub.add_parser("catalog-publish")
    cp.add_argument("--out")
    cp.set_defaults(fn=cmd_catalog_publish)
    sub.add_parser("catalog-pull").set_defaults(fn=cmd_catalog_pull)
    sub.add_parser("purge-uploads").set_defaults(fn=cmd_purge_uploads)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
