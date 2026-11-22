"""Optional: Google Maps rating from the official Google Places API (New).

Google Hotels already shows the Google rating, so this source is only needed if you want the
rating exactly as Google Maps shows it. Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

from __future__ import annotations

from typing import Optional

from ..http import DEFAULT_TIMEOUT, SourceError, check_response, make_session
from ..matching import best_match
from ..models import GOOGLE, Hotel, SiteRating
from .base import PerHotelSource

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.displayName,places.rating,places.userRatingCount,places.location,places.googleMapsUri"


class GooglePlacesSource(PerHotelSource):
    site = GOOGLE

    def __init__(self, api_key: str, **kwargs):
        super().__init__(**kwargs)
        if not api_key:
            raise SourceError("Google Places: GOOGLE_PLACES_API_KEY is missing")
        self.api_key = api_key
        self.session = make_session()

    def rate_one(self, area: str, hotel: Hotel) -> Optional[SiteRating]:
        body: dict = {"textQuery": f"{hotel.name} {area}", "includedType": "lodging", "pageSize": 5}
        if hotel.has_coordinates:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": hotel.latitude, "longitude": hotel.longitude},
                    "radius": 2000.0,
                }
            }
        resp = self.session.post(
            PLACES_URL,
            json=body,
            headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK},
            timeout=DEFAULT_TIMEOUT,
        )
        places = (check_response(resp, "Google Places") or {}).get("places") or []
        place = best_match(
            hotel.name,
            hotel.latitude,
            hotel.longitude,
            places,
            get_name=lambda p: (p.get("displayName") or {}).get("text", ""),
            get_coords=lambda p: (
                (p.get("location") or {}).get("latitude"),
                (p.get("location") or {}).get("longitude"),
            ),
        )
        if not place or place.get("rating") is None:
            return None
        return SiteRating.from_raw(
            GOOGLE,
            place["rating"],
            5,
            reviews=place.get("userRatingCount"),
            url=place.get("googleMapsUri"),
            matched_name=(place.get("displayName") or {}).get("text"),
        )
