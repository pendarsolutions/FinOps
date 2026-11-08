from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FINOPS_", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    database_url: str = f"sqlite:///{(ROOT / 'var' / 'finops-dev.db').as_posix()}"
    redis_url: str | None = None
    jwt_secret: str = "dev-only-change-me-not-for-production-use"
    jwt_ttl_minutes: int = 720
    #: Fernet key (urlsafe base64, 32 bytes) for provider credentials at rest
    credentials_key: str | None = None
    storage_dir: Path = ROOT / "var" / "uploads"
    signed_url_ttl_seconds: int = 300
    invoice_retention_days: int = 30
    max_upload_mb: int = 10
    seed_dir: Path = ROOT / "data" / "seeds"
    #: "inline" runs price syncs in the request (dev/test); "celery" enqueues to the worker
    sync_mode: Literal["inline", "celery"] = "inline"
    #: "anthropic" = Claude via the official SDK; "offline" = deterministic rule-based parser and templated
    #: advisor (no external call - useful where the LLM API is unreachable). Neither path computes prices.
    ai_provider: Literal["anthropic", "offline"] = "offline"
    ai_model: str = "claude-opus-5-5"
    anthropic_api_key: str | None = None
    ai_rate_limit_per_minute: int = 20
    #: signed price catalog. Consumer: set url + public key and this installation stops scraping.
    catalog_url: str | None = None
    catalog_public_key: str | None = None
    #: publisher: scrape as usual and write a signed catalog here after each run
    catalog_publish_dir: Path | None = None
    catalog_signing_key: str | None = None
    #: optional: the collector key on each server then only works from this address
    collector_source_ip: str | None = None
    #: alerts (both optional)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    alert_email_to: str | None = None
    bale_bot_token: str | None = None
    bale_chat_id: str | None = None
    #: the address people open the app at, such as https://finops.example.ir. Links in emails (password reset) are
    #: built from this, never from the request, so a forged Host header can't redirect them. Without it, people ask
    #: an admin to reset their password instead.
    public_url: str | None = None
    password_reset_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    #: open sign-up. The first account can always register; later users are added by an admin.
    allow_registration: bool = False
    login_rate_limit_per_minute: int = 10

    @property
    def is_prod(self) -> bool:
        return self.env in ("staging", "prod")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod:
        if s.jwt_secret.startswith("dev-only-change-me") or len(s.jwt_secret) < 32:
            raise RuntimeError("FINOPS_JWT_SECRET must be set in staging/prod")
        if not s.credentials_key:
            raise RuntimeError("FINOPS_CREDENTIALS_KEY must be set in staging/prod")
        if "finops-dev-password" in s.database_url:
            raise RuntimeError("POSTGRES_PASSWORD must be changed from the development default in staging/prod")
    return s
