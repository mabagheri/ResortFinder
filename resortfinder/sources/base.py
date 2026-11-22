"""Common interface for rating sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from ..http import TTLCache
from ..models import Hotel, SiteRating

ProgressFn = Callable[[int, int], None]  # (done, total)


class RatingSource(ABC):
    """Finds one site's rating for each hotel."""

    site: str = ""

    def __init__(self, cache: Optional[TTLCache] = None):
        self.cache = cache or TTLCache()

    @abstractmethod
    def rate(
        self, area: str, hotels: list[Hotel], progress: Optional[ProgressFn] = None
    ) -> dict[str, Optional[SiteRating]]:
        """Return {hotel.key: SiteRating or None (not found)}."""


class PerHotelSource(RatingSource):
    """A source that needs one lookup per hotel (run in parallel threads)."""

    max_workers = 4

    @abstractmethod
    def rate_one(self, area: str, hotel: Hotel) -> Optional[SiteRating]:
        ...

    def rate(self, area, hotels, progress=None):
        results: dict[str, Optional[SiteRating]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(
                    self.cache.get_or_set,
                    (self.site, hotel.name, hotel.latitude, hotel.longitude),
                    lambda h=hotel: self.rate_one(area, h),
                ): hotel
                for hotel in hotels
            }
            for done, future in enumerate(as_completed(futures), start=1):
                results[futures[future].key] = future.result()
                if progress:
                    progress(done, len(hotels))
        return results
