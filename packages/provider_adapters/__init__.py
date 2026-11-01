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
from .chabokan import ChabokanAdapter
from .feed import FeedAdapter, FeedError, build_feed, generate_signing_key, read_feed, sign_feed
from .iranserver import IranServerAdapter
from .liara import LiaraAdapter
from .manual import ManualPriceAdapter
from .mobinhost import MobinHostAdapter
from .serverir import ServerIrAdapter
from .sync import SyncPlan, plan_sync

#: Adapters with live parsers. ParsPack and Abrha publish only a starting price, so their seed snapshot
#: stays discovery-only and syncs report 'not_implemented'.
ADAPTERS: dict[str, type] = {
    "arvancloud": ArvanCloudAdapter,
    "liara": LiaraAdapter,
    "serverir": ServerIrAdapter,
    "iranserver": IranServerAdapter,
    "chabokan": ChabokanAdapter,
    "mobinhost": MobinHostAdapter,
}

SECOND_WAVE_STATUS = {
    "parspack": "Use the documented ParsPack Cloud Server API for an exact dynamic catalog (not the HTML configurator).",
    "abrha": "Only a starting price is public; needs an authenticated/full source.",
}


def get_adapter(provider_id: str):
    cls = ADAPTERS.get(provider_id)
    return cls() if cls else None


__all__ = [
    "ADAPTERS", "SECOND_WAVE_STATUS", "AdapterHealth", "ArvanCloudAdapter", "ChabokanAdapter", "FeedAdapter", "FeedError", "InventoryConnector", "IranServerAdapter",
    "LiaraAdapter", "ManualPriceAdapter", "MobinHostAdapter", "ParseError", "ProviderAdapter", "RawCatalog", "ServerIrAdapter", "SourceBlockedError",
    "SyncPlan", "build_feed", "generate_signing_key", "get_adapter", "natural_key", "plan_sync", "read_feed", "sign_feed",
]
