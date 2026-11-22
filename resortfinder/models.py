"""Data models shared by every source and by the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Site keys used everywhere (sources, filters, UI columns).
GOOGLE = "google"
TRIPADVISOR = "tripadvisor"
BOOKING = "booking"
EXPEDIA = "expedia"

SITE_LABELS = {
    GOOGLE: "Google Maps",
    TRIPADVISOR: "TripAdvisor",
    BOOKING: "Booking.com",
    EXPEDIA: "Expedia",
}
ALL_SITES = list(SITE_LABELS)


@dataclass
class SiteRating:
    """A hotel's rating on one site, normalized to a 0-5 scale."""

    site: str
    rating: Optional[float]  # 0-5 scale (Booking/Expedia /10 scores are divided by 2)
    raw_rating: Optional[float] = None  # the value exactly as the site shows it
    scale: float = 5.0  # the scale of raw_rating (5 or 10)
    reviews: Optional[int] = None
    url: Optional[str] = None
    matched_name: Optional[str] = None  # the name the site uses, to check the match

    @classmethod
    def from_raw(cls, site: str, raw: Optional[float], scale: float, **kwargs) -> "SiteRating":
        rating = None if raw is None else round(float(raw) * 5.0 / scale, 2)
        return cls(site=site, rating=rating, raw_rating=raw, scale=scale, **kwargs)

    @property
    def display(self) -> str:
        if self.raw_rating is None:
            return "–"
        raw = f"{self.raw_rating:g}/{self.scale:g}"
        return raw if self.scale == 5 else f"{raw} (= {self.rating:.2f}/5)"


@dataclass
class Hotel:
    """A hotel found in the area, plus the ratings collected for it."""

    name: str
    key: str  # stable id (e.g. Google property_token)
    hotel_class: Optional[int] = None  # 2-5 stars, None if unknown
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    link: Optional[str] = None
    price_per_night: Optional[float] = None
    currency: Optional[str] = None
    amenities: list[str] = field(default_factory=list)
    ratings: dict[str, Optional[SiteRating]] = field(default_factory=dict)

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def is_all_inclusive(self) -> Optional[bool]:
        """True/False when the amenity list says so; None when there is no amenity data."""
        if not self.amenities:
            return None
        text = " ".join(self.amenities).lower()
        return "all-inclusive" in text or "all inclusive" in text
