"""TripAdvisor rating from the official TripAdvisor Content API.

Free tier: 5,000 calls/month (each hotel uses 2 calls: search + details).
Docs: https://tripadvisor-content-api.readme.io/reference/overview
"""

from __future__ import annotations

from typing import Optional

from ..http import DEFAULT_TIMEOUT, SourceError, check_response, make_session
from ..matching import best_match
from ..models import TRIPADVISOR, Hotel, SiteRating
from .base import PerHotelSource

BASE_URL = "https://api.content.tripadvisor.com/api/v1"


def _float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> Optional[int]:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


class TripAdvisorSource(PerHotelSource):
    site = TRIPADVISOR

    def __init__(self, api_key: str, referer: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if not api_key:
            raise SourceError("TripAdvisor: TRIPADVISOR_API_KEY is missing")
        self.api_key = api_key
        self.session = make_session()
        self.session.headers["accept"] = "application/json"
        if referer:
            # TripAdvisor keys can be restricted to a domain; send it as Referer.
            self.session.headers["Referer"] = referer

    def _get(self, path: str, **params) -> dict:
        resp = self.session.get(
            f"{BASE_URL}{path}",
            params={"key": self.api_key, "language": "en", **params},
            timeout=DEFAULT_TIMEOUT,
        )
        return check_response(resp, "TripAdvisor") or {}

    def rate_one(self, area: str, hotel: Hotel) -> Optional[SiteRating]:
        params = {"searchQuery": hotel.name, "category": "hotels"}
        if hotel.has_coordinates:
            params["latLong"] = f"{hotel.latitude},{hotel.longitude}"
        else:
            params["searchQuery"] = f"{hotel.name} {area}"
        candidates = self._get("/location/search", **params).get("data") or []
        match = best_match(hotel.name, None, None, candidates, get_name=lambda c: c.get("name", ""))
        if not match:
            return None
        details = self._get(f"/location/{match['location_id']}/details", currency="USD")
        raw = _float(details.get("rating"))
        if raw is None:
            return None
        return SiteRating.from_raw(
            TRIPADVISOR,
            raw,
            5,
            reviews=_int(details.get("num_reviews")),
            url=details.get("web_url"),
            matched_name=details.get("name") or match.get("name"),
        )
