"""Booking.com and Expedia ratings through Apify scrapers ("actors").

Neither site has a public ratings API, so we run a ready-made Apify scraper once for the
whole area, then match its results to our hotels by name and GPS position.
Apify gives $5 of free usage per month. Docs: https://docs.apify.com/api/v2

The actor and its input can be changed in Streamlit secrets without touching code, because
third-party scrapers change their fields from time to time. "{area}" in the input is replaced
by the area typed in the app, and "{max_items}" by the number of results to scrape.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..http import SourceError, check_response, make_session
from ..matching import best_match
from ..models import BOOKING, EXPEDIA, Hotel, SiteRating
from .base import RatingSource

APIFY_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"

DEFAULTS = {
    BOOKING: {
        "actor": "voyager/booking-scraper",
        "input": {"search": "{area}", "maxItems": "{max_items}", "currency": "USD", "language": "en-gb"},
        "scale": 10,
    },
    EXPEDIA: {
        # No default: pick an Expedia/Hotels.com actor on https://apify.com/store and set it in secrets.
        "actor": "",
        "input": {"location": "{area}", "maxItems": "{max_items}"},
        "scale": 10,
    },
}

# Field names used by popular actors; the first one present wins.
NAME_KEYS = ("name", "hotelName", "title")
RATING_KEYS = ("rating", "reviewScore", "guestRating", "score", "reviewsScore", "overallRating")
REVIEWS_KEYS = ("reviews", "reviewsCount", "reviewCount", "numberOfReviews", "totalReviews")
URL_KEYS = ("url", "link", "hotelUrl")
LAT_KEYS = ("lat", "latitude")
LNG_KEYS = ("lng", "lon", "longitude")


def _first(item: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, dict):  # e.g. {"score": 9.1, "count": 1200}
        value = _first(value, ("score", "value", "rating", "average"))
    if isinstance(value, str):
        value = value.replace(",", ".").split("/")[0].strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count(value: Any) -> Optional[int]:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        value = _first(value, ("count", "total"))
    try:
        return int(str(value).replace(",", "").split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def coords(item: dict) -> tuple[Optional[float], Optional[float]]:
    for container in (item, item.get("location") or {}, item.get("coordinates") or {}, item.get("geo") or {}):
        if isinstance(container, dict):
            lat, lng = _number(_first(container, LAT_KEYS)), _number(_first(container, LNG_KEYS))
            if lat is not None and lng is not None:
                return lat, lng
    return None, None


def parse_item(site: str, item: dict, scale: float) -> Optional[SiteRating]:
    raw = _number(_first(item, RATING_KEYS))
    if raw is None:
        return None
    if raw > scale:  # e.g. 86 on a 0-100 scale
        return None
    return SiteRating.from_raw(
        site,
        raw,
        scale,
        reviews=_count(_first(item, REVIEWS_KEYS)),
        url=_first(item, URL_KEYS),
        matched_name=_first(item, NAME_KEYS),
    )


def _fill(template: Any, values: dict[str, Any]) -> Any:
    """Replace "{area}"/"{max_items}" placeholders anywhere in the input JSON."""
    if isinstance(template, dict):
        return {k: _fill(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, values) for v in template]
    if isinstance(template, str):
        for name, value in values.items():
            if template == "{" + name + "}":
                return value  # keep numbers as numbers
            template = template.replace("{" + name + "}", str(value))
    return template


class ApifySource(RatingSource):
    """One Apify actor run per area; results are matched to hotels afterwards."""

    def __init__(
        self,
        site: str,
        token: str,
        actor: Optional[str] = None,
        actor_input: Optional[dict | str] = None,
        scale: Optional[float] = None,
        max_items: int = 150,
        timeout_seconds: int = 280,
        **kwargs,
    ):
        super().__init__(**kwargs)
        defaults = DEFAULTS[site]
        self.site = site
        self.token = token
        self.actor = (actor or defaults["actor"]).replace("/", "~")
        if isinstance(actor_input, str) and actor_input.strip():
            actor_input = json.loads(actor_input)
        self.actor_input = actor_input or defaults["input"]
        self.scale = float(scale or defaults["scale"])
        self.max_items = max_items
        self.timeout = timeout_seconds
        self.session = make_session()
        if not token:
            raise SourceError(f"{site}: APIFY_TOKEN is missing")
        if not self.actor:
            raise SourceError(f"{site}: no Apify actor configured (set {site.upper()}_APIFY_ACTOR)")

    def fetch_area(self, area: str) -> list[dict]:
        body = _fill(self.actor_input, {"area": area, "max_items": self.max_items})

        def run() -> list[dict]:
            resp = self.session.post(
                APIFY_URL.format(actor=self.actor),
                params={"token": self.token, "timeout": self.timeout, "format": "json"},
                json=body,
                timeout=self.timeout + 30,
            )
            data = check_response(resp, f"{self.site} (Apify {self.actor})")
            return data if isinstance(data, list) else []

        return self.cache.get_or_set((self.site, self.actor, json.dumps(body, sort_keys=True)), run)

    def rate(self, area, hotels, progress=None):
        items = self.fetch_area(area)
        results: dict[str, Optional[SiteRating]] = {}
        for done, hotel in enumerate(hotels, start=1):
            item = best_match(
                hotel.name,
                hotel.latitude,
                hotel.longitude,
                items,
                get_name=lambda i: str(_first(i, NAME_KEYS) or ""),
                get_coords=coords,
            )
            results[hotel.key] = parse_item(self.site, item, self.scale) if item else None
            if progress:
                progress(done, len(hotels))
        return results
