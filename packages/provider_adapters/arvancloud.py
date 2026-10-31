"""ArvanCloud adapter.

The official pricing page (https://www.arvancloud.ir/fa/pricing/all) is served behind a JavaScript
bot challenge for non-browser clients, so the HTML adapter detects the interstitial and FAILS the
sync visibly instead of emitting zero or stale prices. The documented ArvanCloud API is the intended
exact source (connector reserved below). Until then the seed snapshot (price date 1405-03-30)
remains the active catalog version and freshness warnings age it.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, SourceBlockedError

CHALLENGE_MARKERS = ("Transferring to the website", "isTehranTimezone", "error-section--waiting")


class ArvanCloudAdapter(HttpAdapterMixin):
    provider_id = "arvancloud"
    source_url = "https://www.arvancloud.ir/fa/pricing/all"
    scope = {("compute_component", "cloud_server"), ("memory_component", "cloud_server"),
             ("storage_component", "cloud_server"), ("gpu_component", "cloud_server"), ("ipv4", "cloud_server"),
             ("network_traffic", "cloud_server")}
    key_skus = {"IR-CPU-STANDARD", "IR-RAM-STANDARD", "IR-ST-HOT_SSD", "IR-IPV4-FIRST"}

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        if any(m in raw.content for m in CHALLENGE_MARKERS):
            raise SourceBlockedError("ArvanCloud pricing page returned a JavaScript bot-challenge interstitial; "
                                     "use the ArvanCloud API connector or a reviewed manual snapshot")
        soup = BeautifulSoup(raw.content, "lxml")
        data = soup.find("script", id="__NEXT_DATA__")
        if data is None:
            raise ParseError("ArvanCloud page structure not recognised (no embedded pricing data)")
        json.loads(data.string or "{}")
        raise ParseError("ArvanCloud page reachable but no verified parser for its embedded data yet")
