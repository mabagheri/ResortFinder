"""The rules that decide whether a hotel passes the user's criteria."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import SITE_LABELS, Hotel

# What to do when a site has no rating for a hotel (not listed, or not matched).
MISSING_EXCLUDE = "exclude"  # strict: the hotel must be rated on every selected site
MISSING_IGNORE = "ignore"  # judge the hotel only on the sites where it was found


@dataclass
class Criteria:
    sites: list[str]  # sites whose rating must meet the minimum
    min_rating: float = 4.5  # on a 0-5 scale (Booking/Expedia /10 are divided by 2)
    per_site_min: dict[str, float] = field(default_factory=dict)  # optional overrides
    hotel_classes: set[int] = field(default_factory=lambda: {2, 3, 4, 5})
    include_unknown_class: bool = False
    min_reviews: int = 0  # ignore ratings based on too few reviews
    missing_policy: str = MISSING_EXCLUDE

    def minimum_for(self, site: str) -> float:
        return self.per_site_min.get(site, self.min_rating)


def check_class(hotel: Hotel, criteria: Criteria) -> list[str]:
    if hotel.hotel_class is None:
        return [] if criteria.include_unknown_class else ["hotel class unknown"]
    if hotel.hotel_class not in criteria.hotel_classes:
        return [f"{hotel.hotel_class}-star is not a selected class"]
    return []


def check_site(hotel: Hotel, site: str, criteria: Criteria) -> list[str]:
    """Reasons this site's rating fails ([] if it passes). Missing data follows missing_policy."""
    label = SITE_LABELS[site]
    rating = hotel.ratings.get(site)
    if rating is None or rating.rating is None:
        return [f"not found on {label}"] if criteria.missing_policy == MISSING_EXCLUDE else []
    if criteria.min_reviews and (rating.reviews or 0) < criteria.min_reviews:
        if criteria.missing_policy == MISSING_EXCLUDE:
            return [f"{label}: only {rating.reviews or 0} reviews"]
        return []
    needed = criteria.minimum_for(site)
    if rating.rating < needed:
        return [f"{label} {rating.display} < {needed:g}"]
    return []


def evaluate(hotel: Hotel, criteria: Criteria) -> list[str]:
    """All the reasons the hotel fails. An empty list means the hotel passes."""
    reasons = check_class(hotel, criteria)
    for site in criteria.sites:
        reasons += check_site(hotel, site, criteria)
    if not reasons and criteria.sites and criteria.missing_policy == MISSING_IGNORE:
        if not any(hotel.ratings.get(s) and hotel.ratings[s].rating is not None for s in criteria.sites):
            reasons.append("no rating found on any selected site")
    return reasons
