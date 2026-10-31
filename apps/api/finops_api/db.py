from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from sqlalchemy import Numeric, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings


class Money(TypeDecorator):
    """Exact decimal column: NUMERIC on PostgreSQL, TEXT on SQLite (SQLite NUMERIC would round-trip via float)."""

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 24, scale: int = 4):
        super().__init__()
        self.precision, self.scale = precision, scale

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(64))
        return dialect.type_descriptor(Numeric(self.precision, self.scale, asdecimal=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("float is not allowed in Money columns")
        value = Decimal(value) if not isinstance(value, Decimal) else value
        return format(value, "f") if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value) if not isinstance(value, Decimal) else value


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if url.startswith("sqlite:///"):
                from pathlib import Path

                Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal = None, None


def SessionLocal() -> Session:  # noqa: N802
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
