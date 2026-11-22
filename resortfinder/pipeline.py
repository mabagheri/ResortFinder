"""Feature 1: find the hotels of an area and keep those that meet the rating criteria.

Order of work (cheapest checks first, to save API quota):
1. Discover hotels in the area (Google Hotels), already filtered by hotel class.
2. Drop hotels that fail on class or on the Google rating (both known from step 1).
3. Look up the remaining hotels on the other selected sites.
4. Apply all criteria and return passed + excluded hotels with the reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .filters import Criteria, check_class, check_site, evaluate
from .http import SourceError
from .models import GOOGLE, SITE_LABELS, Hotel
from .sources.base import RatingSource

StatusFn = Callable[[str, float], None]  # (message, fraction done 0-1)


@dataclass
class Result:
    passed: list[Hotel] = field(default_factory=list)
    excluded: list[tuple[Hotel, list[str]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    discovered: int = 0


def run(
    area: str,
    discovery,
    sources: dict[str, RatingSource],
    criteria: Criteria,
    *,
    all_inclusive: bool = True,
    max_hotels: int = 60,
    discovery_options: Optional[dict] = None,
    status: Optional[StatusFn] = None,
) -> Result:
    status = status or (lambda _msg, _frac: None)
    result = Result()

    status(f"Finding hotels in {area}…", 0.0)
    google_min = criteria.minimum_for(GOOGLE) if GOOGLE in criteria.sites else 0.0
    hotels = discovery.search(
        area,
        all_inclusive=all_inclusive,
        hotel_classes=criteria.hotel_classes,
        min_google_rating=google_min,
        max_hotels=max_hotels,
        **(discovery_options or {}),
    )
    result.discovered = len(hotels)

    # Step 2: cheap pre-filter on data we already have.
    candidates = []
    pre_checked = [GOOGLE] if GOOGLE in criteria.sites and GOOGLE not in sources else []
    for hotel in hotels:
        reasons = check_class(hotel, criteria)
        for site in pre_checked:
            reasons += check_site(hotel, site, criteria)
        if reasons:
            result.excluded.append((hotel, reasons))
        else:
            candidates.append(hotel)

    # Step 3: other sites, one at a time.
    sites = [s for s in criteria.sites if s in sources]
    for index, site in enumerate(sites):
        label = SITE_LABELS[site]
        base = 0.1 + 0.85 * index / max(len(sites), 1)
        span = 0.85 / max(len(sites), 1)

        def progress(done: int, total: int, label=label, base=base, span=span) -> None:
            status(f"Checking {label}: {done}/{total}", base + span * done / max(total, 1))

        status(f"Checking {label}…", base)
        try:
            ratings = sources[site].rate(area, candidates, progress)
        except SourceError as exc:
            result.warnings.append(f"{label} was skipped: {exc}")
            continue
        for hotel in candidates:
            hotel.ratings[site] = ratings.get(hotel.key)

    # Step 4: final decision. A site that failed completely is not held against hotels.
    failed_sites = {s for s in sites if any(w.startswith(SITE_LABELS[s]) for w in result.warnings)}
    final = Criteria(**{**criteria.__dict__, "sites": [s for s in criteria.sites if s not in failed_sites]})
    for hotel in candidates:
        reasons = evaluate(hotel, final)
        if reasons:
            result.excluded.append((hotel, reasons))
        else:
            result.passed.append(hotel)

    result.passed.sort(key=lambda h: _average(h, final.sites), reverse=True)
    status("Done", 1.0)
    return result


def _average(hotel: Hotel, sites: list[str]) -> float:
    values = [hotel.ratings[s].rating for s in sites if hotel.ratings.get(s) and hotel.ratings[s].rating is not None]
    return sum(values) / len(values) if values else 0.0


def average_rating(hotel: Hotel, sites: list[str]) -> Optional[float]:
    value = _average(hotel, sites)
    return round(value, 2) if value else None
