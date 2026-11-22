"""Match the same hotel across sites using its name and GPS position."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Callable, Iterable, Optional, TypeVar

from rapidfuzz import fuzz

T = TypeVar("T")

# Words that every resort name shares; they make different hotels look alike.
_STOPWORDS = {
    "the", "a", "an", "and", "by", "at", "de", "la", "el", "los", "las",
    "hotel", "hotels", "resort", "resorts", "spa", "suites", "suite",
    "all", "inclusive", "allinclusive", "adults", "only", "adult", "family",
    "beach", "club", "collection", "experience", "&",
}

# Name similarity (0-100) needed to accept a match.
MIN_SCORE_WITH_DISTANCE = 70  # used when both positions are known and close
MIN_SCORE_NAME_ONLY = 88  # used when a position is missing
MAX_DISTANCE_KM = 1.5  # beyond this, two "close" names are treated as different hotels


def normalize_name(name: str) -> str:
    """Lowercase, strip accents and punctuation, drop generic words."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("all-inclusive", "allinclusive").replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    kept = [w for w in words if w not in _STOPWORDS]
    return " ".join(kept or words)


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    # Small typos/plurals in longer words ("palladium"/"paladium"), never in short ones.
    return min(len(a), len(b)) >= 5 and fuzz.ratio(a, b) >= 85


def name_similarity(a: str, b: str) -> float:
    """0-100. Compares whole words, so sister hotels like "Hyatt Ziva" / "Hyatt Zilara" differ."""
    wa, wb = normalize_name(a).split(), normalize_name(b).split()
    if not wa or not wb:
        return 0.0
    unmatched_b = list(wb)
    matched = 0
    for word in wa:
        hit = next((w for w in unmatched_b if _same_word(word, w)), None)
        if hit is not None:
            unmatched_b.remove(hit)
            matched += 1
    extra_a, extra_b = len(wa) - matched, len(unmatched_b)
    if extra_a and extra_b:
        # Each name has a word the other lacks ("ziva" vs "zilara"): treat as different hotels.
        return min(60.0, 100.0 * matched / max(len(wa), len(wb)))
    # One name may just be longer ("Iberostar Cancun" vs "Iberostar Selection Cancun").
    return 100.0 * (matched / min(len(wa), len(wb)) + matched / max(len(wa), len(wb))) / 2


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def best_match(
    name: str,
    lat: Optional[float],
    lon: Optional[float],
    candidates: Iterable[T],
    get_name: Callable[[T], str],
    get_coords: Callable[[T], tuple[Optional[float], Optional[float]]] = lambda _: (None, None),
) -> Optional[T]:
    """Return the candidate that is the same hotel, or None if no candidate is close enough."""
    best: Optional[T] = None
    best_score = -1.0
    for cand in candidates:
        score = name_similarity(name, get_name(cand))
        clat, clon = get_coords(cand)
        if None not in (lat, lon, clat, clon):
            distance = haversine_km(lat, lon, clat, clon)
            if distance > MAX_DISTANCE_KM:
                continue
            needed = MIN_SCORE_WITH_DISTANCE
            score += (MAX_DISTANCE_KM - distance) * 5  # small bonus for being closer
        else:
            needed = MIN_SCORE_NAME_ONLY
        if score >= needed and score > best_score:
            best, best_score = cand, score
    return best
