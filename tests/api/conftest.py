import os

import pytest


@pytest.fixture(scope="session")
def api_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pendar")
    os.environ["PENDAR_DATABASE_URL"] = f"sqlite:///{(tmp / 'test.db').as_posix()}"
    os.environ["PENDAR_STORAGE_DIR"] = str(tmp / "uploads")
    os.environ["PENDAR_ENV"] = "test"
    os.environ["PENDAR_AI_PROVIDER"] = "offline"
    os.environ["PENDAR_SYNC_MODE"] = "inline"
    from pendar_api.config import get_settings
    from pendar_api.db import Base, SessionLocal, get_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    import pendar_api.orm  # noqa: F401
    from pendar_api.catalog_store import seed_pricing

    Base.metadata.create_all(get_engine())
    with SessionLocal() as db:
        seed_pricing(db, get_settings().seed_dir)
    yield tmp
    reset_engine()


@pytest.fixture(scope="session")
def client(api_env):
    from fastapi.testclient import TestClient

    from pendar_api.main import create_app

    return TestClient(create_app())


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/v1/auth/register", json={"email": "owner@example.ir", "password": "correct-horse-1",
                                                   "name": "Owner", "organization_name": "Acme"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
