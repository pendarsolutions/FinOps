import pytest

from pricing_engine import Resource, load_seed_snapshot
from pricing_engine.catalog import SEED_DIR, load_json


@pytest.fixture(scope="session")
def snapshot():
    return load_seed_snapshot()


@pytest.fixture(scope="session")
def sample_resources():
    inv = load_json(SEED_DIR / "sample_inventory.json")
    return [Resource(id=r["external_ref"], **{k: v for k, v in r.items() if k != "external_ref"})
            for r in inv["resources"]]


def make(**kw) -> Resource:
    kw.setdefault("id", "r1")
    return Resource(**kw)
