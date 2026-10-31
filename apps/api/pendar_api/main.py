from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

import fastapi.encoders
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .platform import configure_logging
from .routers import analysis, auth, catalog, integrations, inventories

# Money must never become a binary float on the wire: encode every Decimal as an exact string.
fastapi.encoders.ENCODERS_BY_TYPE[Decimal] = lambda d: format(d.normalize(), "f")

log = logging.getLogger("pendar.api")


def create_app() -> FastAPI:
    configure_logging()
    s = get_settings()
    app = FastAPI(title="Pendar FinOps API", version="0.1.0",
                  description="Iran-first FinOps. All prices/savings come from the deterministic engine; "
                              "money fields are exact decimal strings in Toman.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info("request", extra={"request_id": rid, "path": request.url.path, "method": request.method,
                                   "status": response.status_code,
                                   "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    for r in (auth.router, catalog.router, inventories.router, analysis.router, integrations.router):
        app.include_router(r)
    return app


app = create_app()
