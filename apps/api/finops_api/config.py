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
