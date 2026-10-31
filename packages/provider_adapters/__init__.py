"""Provider adapters: fetch official sources, normalize to CatalogItem, plan guarded syncs."""

from .arvancloud import ArvanCloudAdapter
from .base import (
    AdapterHealth,
    InventoryConnector,
    ParseError,
    ProviderAdapter,
    RawCatalog,
    SourceBlockedError,
    natural_key,
)
from .iranserver import IranServerAdapter
from .liara import LiaraAdapter
from .serverir import ServerIrAdapter
from .sync import SyncPlan, plan_sync

#: First-wave adapters with live parsers. Second-wave providers (chabokan, parspack, mobinhost, abrha)
#: have no live parser yet: their seed snapshot stays active and syncs report 'not_implemented'.
ADAPTERS: dict[str, type] = {
    "arvancloud": ArvanCloudAdapter,
    "liara": LiaraAdapter,
    "serverir": ServerIrAdapter,
    "iranserver": IranServerAdapter,
}

SECOND_WAVE_STATUS = {
    "chabokan": "Public plan list is large and dynamic; seed rows only. Next: official plan scraper.",
    "parspack": "Use the documented ParsPack Cloud Server API for an exact dynamic catalog (not the HTML configurator).",
    "mobinhost": "Server-rendered plan pages; parser not yet written. Seed rows only.",
    "abrha": "Only a starting price is public; needs an authenticated/full source.",
}


def get_adapter(provider_id: str):
    cls = ADAPTERS.get(provider_id)
    return cls() if cls else None


__all__ = [
    "ADAPTERS", "SECOND_WAVE_STATUS", "AdapterHealth", "ArvanCloudAdapter", "InventoryConnector", "IranServerAdapter",
    "LiaraAdapter", "ParseError", "ProviderAdapter", "RawCatalog", "ServerIrAdapter", "SourceBlockedError",
    "SyncPlan", "get_adapter", "natural_key", "plan_sync",
]
