"""Feature 1 in two steps.

collect()        Uses the APIs. Finds ALL hotels of an area (every class, every rating) and
                 looks each one up on the chosen sites. Its result is saved per area
                 (see store.py), so this runs once per area, not once per search.
apply_filters()  No API calls. Applies hotel class / minimum rating / etc. to saved hotels,
                 so changing the criteria is free and instant.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .filters import Criteria, evaluate
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
    sites_used: list[str] = field(default_factory=list)


def collect(
    area: str,
    discovery,
    sources: dict[str, RatingSource],
    *,
    all_inclusive: bool = True,
    max_hotels: int = 100,
    discovery_options: Optional[dict] = None,
    existing: Optional[list[Hotel]] = None,
    only_sites: Optional[Iterable[str]] = None,
    status: Optional[StatusFn] = None,
) -> tuple[list[Hotel], list[str]]:
    """Return (hotels with ratings, warnings).

    existing:   hotels already saved for the area; when given, no new hotel search is made.
    only_sites: look up only these sites (e.g. the ones missing from the saved file).
    """
    status = status or (lambda _msg, _frac: None)
    today = dt.date.today().isoformat()
    warnings: list[str] = []

    if existing is None:
        status(f"Finding all hotels in {area}…", 0.0)
        hotels = discovery.search(
            area,
            all_inclusive=all_inclusive,
            hotel_classes=(2, 3, 4, 5),  # everything: class is filtered later, for free
            min_google_rating=0.0,
            max_hotels=max_hotels,
            **(discovery_options or {}),
        )
        for hotel in hotels:
            hotel.checked[GOOGLE] = today  # Google Hotels gives the Google rating
    else:
        hotels = existing

    wanted = set(only_sites) if only_sites is not None else set(sources)
    sites = [s for s in sources if s in wanted]
    for index, site in enumerate(sites):
        label = SITE_LABELS[site]
        base = 0.1 + 0.85 * index / len(sites)
        span = 0.85 / len(sites)

        def progress(done: int, total: int, label=label, base=base, span=span) -> None:
            status(f"Checking {label}: {done}/{total}", base + span * done / max(total, 1))

        status(f"Checking {label}…", base)
        try:
            ratings = sources[site].rate(area, hotels, progress)
        except SourceError as exc:
            warnings.append(f"{label} was skipped: {exc}")
            continue
        for hotel in hotels:
            hotel.ratings[site] = ratings.get(hotel.key)
            hotel.checked[site] = today

    status("Done", 1.0)
    return hotels, warnings


def apply_filters(hotels: list[Hotel], criteria: Criteria, *, all_inclusive_only: bool = False) -> Result:
    """Split hotels into passed / excluded. Sites never checked for this area are skipped."""
    result = Result(discovered=len(hotels))
    checked_sites = [s for s in criteria.sites if any(s in h.checked for h in hotels)]
    unchecked = [SITE_LABELS[s] for s in criteria.sites if s not in checked_sites]
    if unchecked and hotels:
        result.warnings.append(
            f"No saved data for {', '.join(unchecked)} in this area, so it was not used. "
            "Use “Fetch missing sites” to add it."
        )
    final = Criteria(**{**criteria.__dict__, "sites": checked_sites})
    result.sites_used = checked_sites

    for hotel in hotels:
        reasons = evaluate(hotel, final)
        if all_inclusive_only and hotel.is_all_inclusive is False:
            reasons.append("not all-inclusive")
        if reasons:
            result.excluded.append((hotel, reasons))
        else:
            result.passed.append(hotel)
    result.passed.sort(key=lambda h: average_rating(h, checked_sites) or 0, reverse=True)
    return result


def average_rating(hotel: Hotel, sites: list[str]) -> Optional[float]:
    values = [hotel.ratings[s].rating for s in sites if hotel.ratings.get(s) and hotel.ratings[s].rating is not None]
    return round(sum(values) / len(values), 2) if values else None
