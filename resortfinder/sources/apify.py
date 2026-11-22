"""Booking.com, TripAdvisor and Expedia ratings through Apify scrapers ("actors").

These sites have no free public ratings API (TripAdvisor's official API asks for a card), so we run a ready-made Apify scraper once for the
whole area, then match its results to our hotels by name and GPS position.
Apify gives $5 of free usage per month. Docs: https://docs.apify.com/api/v2

The actor and its input can be changed in Streamlit secrets without touching code, because
third-party scrapers change their fields from time to time. "{area}" in the input is replaced
by the area typed in the app, and "{max_items}" by the number of results to scrape.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..http import SourceError, check_response, make_session
from ..matching import best_match
from ..models import BOOKING, EXPEDIA, SITE_LABELS, TRIPADVISOR, Hotel, SiteRating
from .base import RatingSource

APIFY_API = "https://api.apify.com/v2"
FINISHED = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}

DEFAULTS = {
    BOOKING: {
        "actor": "voyager/booking-scraper",
        "input": {"search": "{area}", "maxItems": "{max_items}", "currency": "USD", "language": "en-gb"},
        "scale": 10,
    },
    TRIPADVISOR: {
        "actor": "maxcopell/tripadvisor",
        "input": {
            "query": "{area}",
            "maxItemsPerQuery": "{max_items}",
            "includeHotels": True,
            "includeRestaurants": False,
            "includeAttractions": False,
            "includeVacationRentals": False,
            "language": "en",
            "currency": "USD",
        },
        "scale": 5,
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
URL_KEYS = ("url", "webUrl", "link", "hotelUrl")
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
        timeout_seconds: int = 15 * 60,
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
        """Run the scraper for the area and return its results (cached, except failures)."""
        body = _fill(self.actor_input, {"area": area, "max_items": self.max_items})
        return self.cache.get_or_set(self._cache_key(area), lambda: self._run(body))

    def _cache_key(self, area: str) -> tuple:
        body = _fill(self.actor_input, {"area": area, "max_items": self.max_items})
        return (self.site, self.actor, json.dumps(body, sort_keys=True))

    def _run(self, body: dict) -> list[dict]:
        """Start the scraper, wait until it finishes, then download its results."""
        name = f"{SITE_LABELS[self.site]} (Apify {self.actor})"
        params = {"token": self.token}
        resp = self.session.post(f"{APIFY_API}/acts/{self.actor}/runs", params=params, json=body, timeout=60)
        run = (check_response(resp, name) or {}).get("data") or {}
        deadline = time.monotonic() + self.timeout
        while run.get("status") not in FINISHED:
            if time.monotonic() > deadline:
                raise SourceError(f"{name}: still running after {self.timeout // 60} minutes; try again later")
            resp = self.session.get(f"{APIFY_API}/actor-runs/{run['id']}",
                                    params={**params, "waitForFinish": 60}, timeout=90)
            run = (check_response(resp, name) or {}).get("data") or {}
        if run["status"] != "SUCCEEDED":
            raise SourceError(f"{name}: the scraper run ended with status {run['status']}")
        resp = self.session.get(f"{APIFY_API}/datasets/{run['defaultDatasetId']}/items",
                                params={**params, "format": "json", "clean": "true"}, timeout=120)
        data = check_response(resp, name)
        return data if isinstance(data, list) else []

    def _check_usable(self, items: list[dict], area: str, label: str) -> None:
        """Explain clearly when the scraper's output can't be used (wrong input or changed fields)."""
        if not items:
            raise SourceError(
                f"{label}: the Apify scraper {self.actor} returned no results for '{area}'. "
                f"Check its input ({self.site.upper()}_APIFY_INPUT) on its Apify page."
            )
        if not any(parse_item(self.site, i, self.scale) for i in items):
            fields = sorted({k for i in items[:5] for k in i})[:25]
            raise SourceError(
                f"{label}: the Apify scraper {self.actor} returned {len(items)} results, but none had a "
                f"rating field this app knows. Fields received: {', '.join(fields)}"
            )

    def rate(self, area, hotels, progress=None):
        items = [i for i in self.fetch_area(area) if isinstance(i, dict)]
        label = SITE_LABELS[self.site]
        try:
            self._check_usable(items, area, label)
        except SourceError:
            self.cache.discard(self._cache_key(area))  # so a retry really runs the scraper again
            raise
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
