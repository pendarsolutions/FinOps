"""Cross-cutting platform services: structured logs, rate limiting, private storage, secret encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from .config import get_settings

# --------------------------------------------------------------------------- logging

SECRET_PATTERNS = [re.compile(p, re.I) for p in (r"(authorization|password|secret|token|api[_-]?key)\"?\s*[:=]\s*\"?[^\s\",]+",
                                                 r"bearer\s+[a-z0-9\-_.]+")]


def redact(text: str) -> str:
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": datetime.now(UTC).isoformat(), "level": record.levelname, "logger": record.name,
                   "msg": redact(record.getMessage())}
        for key in ("request_id", "path", "method", "status", "duration_ms", "org_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).handlers = [handler]


# --------------------------------------------------------------------------- rate limit


class RateLimiter:
    """Sliding-window limiter. Uses Redis when configured (shared across API replicas), else in-process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._redis = None
        url = get_settings().redis_url
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url)
            except Exception:  # noqa: BLE001
                self._redis = None

    def check(self, key: str, limit: int, window_s: int = 60) -> None:
        if self._redis is not None:
            try:
                bucket = f"rl:{key}:{int(time.time() // window_s)}"
                n = self._redis.incr(bucket)
                self._redis.expire(bucket, window_s)
                if n > limit:
                    raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "AI rate limit exceeded")
                return
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001 - fall back to local limiter
                pass
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "AI rate limit exceeded")
            q.append(now)


_limiter: RateLimiter | None = None


def limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


# --------------------------------------------------------------------------- private storage

ALLOWED_UPLOADS = {
    "application/pdf": (b"%PDF-",),
    "text/csv": (),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


def validate_upload(filename: str, content_type: str, data: bytes) -> str:
    s = get_settings()
    if len(data) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file larger than {s.max_upload_mb} MB")
    ext = Path(filename).suffix.lower()
    kind = {".pdf": "application/pdf", ".csv": "text/csv", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg"}.get(ext)
    if kind is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "only PDF, CSV, PNG, JPG are accepted")
    magic = ALLOWED_UPLOADS[kind]
    if magic and not any(data.startswith(m) for m in magic):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "file content does not match its extension")
    if kind == "text/csv":
        try:
            data[:4096].decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "CSV must be UTF-8 text") from exc
    return kind


def store_private(org_id: str, upload_id: str, data: bytes) -> str:
    base = get_settings().storage_dir / org_id
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{upload_id}.bin"
    path.write_bytes(data)
    return str(path)


def sign_download(upload_id: str, expires_at: int | None = None) -> str:
    s = get_settings()
    exp = expires_at or int(time.time()) + s.signed_url_ttl_seconds
    sig = hmac.new(s.jwt_secret.encode(), f"{upload_id}:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"/api/v1/uploads/{upload_id}/download?exp={exp}&sig={sig}"


def verify_download(upload_id: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    expected = hmac.new(get_settings().jwt_secret.encode(), f"{upload_id}:{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# --------------------------------------------------------------------------- secrets at rest


def _fernet() -> Fernet:
    key = get_settings().credentials_key
    if not key:
        # dev/test only: derive a stable key from the JWT secret (prod refuses to start without a key)
        key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().jwt_secret.encode()).digest()).decode()
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
