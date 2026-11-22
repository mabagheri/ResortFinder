"""Find the hotels of an area with Google Hotels (through SerpApi).

Gives, for every hotel: name, hotel class (2-5 stars), Google rating, review count,
GPS position, amenities and a price. Docs: https://serpapi.com/google-hotels-api
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from ..http import DEFAULT_TIMEOUT, SourceError, TTLCache, check_response, make_session
from ..models import GOOGLE, Hotel, SiteRating

SERPAPI_URL = "https://serpapi.com/search.json"


def serpapi_rating_filter(min_rating: float) -> Optional[str]:
    """SerpApi only offers 3.5+ (7), 4.0+ (8) and 4.5+ (9)."""
    if min_rating >= 4.5:
        return "9"
    if min_rating >= 4.0:
        return "8"
    if min_rating >= 3.5:
        return "7"
    return None


def parse_property(item: dict, currency: str) -> Optional[Hotel]:
    """Convert one entry of SerpApi's `properties` array into a Hotel."""
    name = item.get("name")
    if not name:
        return None
    if item.get("type") and item["type"].lower() != "hotel":
        return None  # skip vacation rentals
    gps = item.get("gps_coordinates") or {}
    rate = item.get("rate_per_night") or {}
    hotel_class = item.get("extracted_hotel_class")
    if hotel_class is None and isinstance(item.get("hotel_class"), str):
        digits = [c for c in item["hotel_class"] if c.isdigit()]
        hotel_class = int(digits[0]) if digits else None
    rating = item.get("overall_rating")
    hotel = Hotel(
        name=name,
        key=item.get("property_token") or name,
        hotel_class=int(hotel_class) if hotel_class else None,
        latitude=gps.get("latitude"),
        longitude=gps.get("longitude"),
        address=item.get("description"),
        link=item.get("link"),
        price_per_night=rate.get("extracted_lowest"),
        currency=currency,
        amenities=list(item.get("amenities") or []),
    )
    hotel.ratings[GOOGLE] = SiteRating.from_raw(
        GOOGLE,
        rating,
        5,
        reviews=item.get("reviews"),
        url=item.get("link"),
        matched_name=name,
    )
    return hotel


class GoogleHotelsDiscovery:
    """Lists the hotels of an area. Needs a SerpApi key (free plan: 250 searches/month)."""

    def __init__(self, api_key: str, cache: Optional[TTLCache] = None):
        if not api_key:
            raise SourceError("Google Hotels: SERPAPI_KEY is missing")
        self.api_key = api_key
        self.session = make_session()
        self.cache = cache or TTLCache(ttl_seconds=24 * 3600)

    def search(
        self,
        area: str,
        *,
        all_inclusive: bool = True,
        hotel_classes: Iterable[int] = (2, 3, 4, 5),
        min_google_rating: float = 0.0,
        check_in: Optional[dt.date] = None,
        nights: int = 1,
        adults: int = 2,
        currency: str = "USD",
        max_hotels: int = 60,
    ) -> list[Hotel]:
        check_in = check_in or dt.date.today() + dt.timedelta(days=30)
        query = f"all inclusive resorts in {area}" if all_inclusive else f"hotels in {area}"
        params = {
            "engine": "google_hotels",
            "q": query,
            "check_in_date": check_in.isoformat(),
            "check_out_date": (check_in + dt.timedelta(days=nights)).isoformat(),
            "adults": adults,
            "currency": currency,
            "hl": "en",
            "gl": "us",
            "sort_by": "8",  # highest rating first
        }
        classes = sorted(set(hotel_classes))
        if classes and classes != [2, 3, 4, 5]:
            params["hotel_class"] = ",".join(map(str, classes))
        rating_filter = serpapi_rating_filter(min_google_rating)
        if rating_filter:
            params["rating"] = rating_filter

        key = tuple(sorted(params.items())) + (max_hotels,)
        return self.cache.get_or_set(key, lambda: self._fetch_all(params, currency, max_hotels))

    def _fetch_all(self, params: dict, currency: str, max_hotels: int) -> list[Hotel]:
        hotels: dict[str, Hotel] = {}
        page_params = dict(params)
        for _ in range(10):  # ~20 hotels per page
            resp = self.session.get(
                SERPAPI_URL, params={**page_params, "api_key": self.api_key}, timeout=DEFAULT_TIMEOUT
            )
            data = check_response(resp, "Google Hotels (SerpApi)")
            for item in data.get("properties") or []:
                hotel = parse_property(item, currency)
                if hotel and hotel.key not in hotels:
                    hotels[hotel.key] = hotel
            token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not token or len(hotels) >= max_hotels:
                break
            page_params = {**params, "next_page_token": token}
        return list(hotels.values())[:max_hotels]
