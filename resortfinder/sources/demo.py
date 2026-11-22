"""Demo mode: fictional hotels and ratings, so the app works without any API key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from ..models import GOOGLE, Hotel, SiteRating
from .base import RatingSource

DEMO_FILE = Path(__file__).resolve().parents[2] / "data" / "demo_hotels.json"
SCALES = {"google": 5, "tripadvisor": 5, "booking": 10, "expedia": 10}


def _load() -> list[dict]:
    return json.loads(DEMO_FILE.read_text())["hotels"]


def _rating(site: str, entry: Optional[dict]) -> Optional[SiteRating]:
    if not entry:
        return None
    return SiteRating.from_raw(site, entry["rating"], SCALES[site], reviews=entry.get("reviews"))


class DemoDiscovery:
    def search(
        self,
        area: str,
        *,
        all_inclusive: bool = True,
        hotel_classes: Iterable[int] = (2, 3, 4, 5),
        max_hotels: int = 60,
        **_ignored,
    ) -> list[Hotel]:
        classes = set(hotel_classes)
        hotels = []
        for i, row in enumerate(_load()):
            if all_inclusive and not row["all_inclusive"]:
                continue
            if row["hotel_class"] not in classes:
                continue
            hotel = Hotel(
                name=row["name"],
                key=f"demo-{i}",
                hotel_class=row["hotel_class"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                price_per_night=row["price_per_night"],
                currency="USD",
                amenities=["All-inclusive available"] if row["all_inclusive"] else [],
            )
            hotel.ratings[GOOGLE] = _rating(GOOGLE, row["ratings"][GOOGLE])
            hotels.append(hotel)
        return hotels[:max_hotels]


class DemoRatingSource(RatingSource):
    def __init__(self, site: str):
        super().__init__()
        self.site = site
        self._by_name = {row["name"]: row for row in _load()}

    def rate(self, area, hotels, progress=None):
        out = {}
        for done, hotel in enumerate(hotels, start=1):
            row = self._by_name.get(hotel.name)
            out[hotel.key] = _rating(self.site, row["ratings"].get(self.site)) if row else None
            if progress:
                progress(done, len(hotels))
        return out
