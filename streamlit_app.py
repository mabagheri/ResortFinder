"""ResortFinder – Feature 1: find hotels in an area that are rated highly on every site.

Run locally:   streamlit run streamlit_app.py
API keys go in .streamlit/secrets.toml (see secrets.toml.example) or in the
"Secrets" box of Streamlit Community Cloud.
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import streamlit as st

from resortfinder import pipeline
from resortfinder.filters import MISSING_EXCLUDE, MISSING_IGNORE, Criteria
from resortfinder.http import SourceError, TTLCache
from resortfinder.models import ALL_SITES, BOOKING, EXPEDIA, GOOGLE, SITE_LABELS, TRIPADVISOR
from resortfinder.sources.apify import ApifySource
from resortfinder.sources.demo import DemoDiscovery, DemoRatingSource
from resortfinder.sources.google_hotels import GoogleHotelsDiscovery
from resortfinder.sources.google_places import GooglePlacesSource
from resortfinder.sources.tripadvisor import TripAdvisorSource

st.set_page_config(page_title="ResortFinder", page_icon="🏝️", layout="wide")


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets.toml at all
        value = None
    return str(value or os.environ.get(name, default)).strip()


@st.cache_resource
def shared_cache() -> TTLCache:
    """Survives reruns, so the same search doesn't use API quota twice."""
    return TTLCache(ttl_seconds=7 * 24 * 3600)


KEYS = {
    "serpapi": secret("SERPAPI_KEY"),
    "places": secret("GOOGLE_PLACES_API_KEY"),
    "tripadvisor": secret("TRIPADVISOR_API_KEY"),
    "apify": secret("APIFY_TOKEN"),
}
EXPEDIA_ACTOR = secret("EXPEDIA_APIFY_ACTOR")


def site_available(site: str) -> tuple[bool, str]:
    """Whether a site can be used in live mode, and what is missing if not."""
    if site == GOOGLE:
        return bool(KEYS["serpapi"]), "SERPAPI_KEY"
    if site == TRIPADVISOR:
        return bool(KEYS["tripadvisor"]), "TRIPADVISOR_API_KEY"
    if site == BOOKING:
        return bool(KEYS["apify"]), "APIFY_TOKEN"
    if site == EXPEDIA:
        return bool(KEYS["apify"] and EXPEDIA_ACTOR), "APIFY_TOKEN + EXPEDIA_APIFY_ACTOR"
    return False, ""


def build_sources(live: bool, sites: list[str], max_items: int):
    cache = shared_cache()
    if not live:
        return DemoDiscovery(), {s: DemoRatingSource(s) for s in sites if s != GOOGLE}
    discovery = GoogleHotelsDiscovery(KEYS["serpapi"], cache=cache)
    sources = {}
    if GOOGLE in sites and KEYS["places"]:
        sources[GOOGLE] = GooglePlacesSource(KEYS["places"], cache=cache)
    if TRIPADVISOR in sites:
        sources[TRIPADVISOR] = TripAdvisorSource(
            KEYS["tripadvisor"], referer=secret("TRIPADVISOR_REFERER") or None, cache=cache
        )
    if BOOKING in sites:
        sources[BOOKING] = ApifySource(
            BOOKING,
            KEYS["apify"],
            actor=secret("BOOKING_APIFY_ACTOR") or None,
            actor_input=secret("BOOKING_APIFY_INPUT") or None,
            max_items=max_items,
            cache=cache,
        )
    if EXPEDIA in sites:
        sources[EXPEDIA] = ApifySource(
            EXPEDIA,
            KEYS["apify"],
            actor=EXPEDIA_ACTOR,
            actor_input=secret("EXPEDIA_APIFY_INPUT") or None,
            scale=float(secret("EXPEDIA_RATING_SCALE", "10")),
            max_items=max_items,
            cache=cache,
        )
    return discovery, sources


def stars(n) -> str:
    return "★" * int(n) if n else "?"


def hotels_table(hotels, sites, reasons=None) -> pd.DataFrame:
    rows = []
    for i, h in enumerate(hotels):
        row = {
            "Hotel": h.name,
            "Class": stars(h.hotel_class),
            "Avg /5": pipeline.average_rating(h, sites),
        }
        for site in ALL_SITES:
            r = h.ratings.get(site)
            if site not in sites and r is None:
                continue
            row[f"{SITE_LABELS[site]} /5"] = r.rating if r else None
            row[f"{SITE_LABELS[site]} reviews"] = r.reviews if r else None
        row["From $/night"] = h.price_per_night
        if reasons is not None:
            row["Why excluded"] = "; ".join(reasons[i])
        row["Google Hotels"] = h.link
        for site in sites:
            r = h.ratings.get(site)
            if r and r.url and site != GOOGLE:
                row[f"{SITE_LABELS[site]} link"] = r.url
        rows.append(row)
    return pd.DataFrame(rows)


def link_columns(df: pd.DataFrame) -> dict:
    config = {c: st.column_config.LinkColumn(c, display_text="open") for c in df.columns if "link" in c or c == "Google Hotels"}
    for c in df.columns:
        if c.endswith("/5"):
            config[c] = st.column_config.NumberColumn(c, format="%.2f")
        if c.endswith("$/night"):
            config[c] = st.column_config.NumberColumn(c, format="$%d")
    return config


# ---------------------------------------------------------------- sidebar
st.title("🏝️ ResortFinder")
st.caption("Find the hotels of an area that meet your minimum rating on Google Maps, TripAdvisor, Booking.com and Expedia.")

with st.sidebar:
    st.header("Search")
    live_possible = bool(KEYS["serpapi"])
    mode = st.radio(
        "Data",
        ["Live", "Demo (fictional data)"],
        index=0 if live_possible else 1,
        disabled=not live_possible,
        help="Live mode needs at least SERPAPI_KEY in the app secrets.",
    )
    live = mode == "Live"
    area = st.text_input("Area", value="Cancun", help="City or region, e.g. Cancun, Riviera Maya, Punta Cana")
    all_inclusive = st.toggle("All-inclusive resorts only", value=True)
    classes = st.multiselect(
        "Hotel class", [2, 3, 4, 5], default=[4, 5], format_func=lambda n: f"{n} stars {stars(n)}"
    )
    include_unknown_class = st.checkbox("Include hotels without a class", value=False)

    st.header("Ratings")
    min_rating = st.slider("Minimum rating (out of 5)", 3.0, 5.0, 4.5, 0.1,
                           help="Booking.com and Expedia scores are out of 10; they are divided by 2 (9.0/10 = 4.5/5).")
    chosen_sites = []
    for site in ALL_SITES:
        ok, needs = site_available(site) if live else (True, "")
        checked = st.checkbox(SITE_LABELS[site], value=ok, disabled=not ok,
                              help=None if ok else f"Add {needs} to the app secrets to enable.")
        if checked and ok:
            chosen_sites.append(site)

    with st.expander("More options"):
        per_site = {}
        if st.checkbox("Different minimum per site"):
            for site in chosen_sites:
                per_site[site] = st.number_input(f"{SITE_LABELS[site]} minimum /5", 0.0, 5.0, min_rating, 0.1)
        missing = st.radio(
            "If a hotel is not found on a site",
            [MISSING_EXCLUDE, MISSING_IGNORE],
            format_func={MISSING_EXCLUDE: "Exclude it (strict)", MISSING_IGNORE: "Judge it on the other sites"}.get,
        )
        min_reviews = st.number_input("Ignore ratings with fewer reviews than", 0, 5000, 50, 10)
        max_hotels = st.slider("Max hotels to check", 10, 200, 60, 10,
                               help="More hotels = more API calls (TripAdvisor uses 2 per hotel).")
        check_in = st.date_input("Sample check-in date", dt.date.today() + dt.timedelta(days=30),
                                 help="Google Hotels needs dates to search; ratings don't depend on them.")
        adults = st.number_input("Adults", 1, 8, 2)
        if st.button("Clear cached results"):
            shared_cache().clear()
            st.toast("Cache cleared")

    go = st.button("Find resorts", type="primary", use_container_width=True)

if not live_possible:
    st.info("No API keys found, so the app is running on **fictional demo data**. "
            "Add keys in the app's secrets (see the README) to search real hotels.", icon="ℹ️")

# ---------------------------------------------------------------- run
if go:
    if not classes and not include_unknown_class:
        st.error("Pick at least one hotel class.")
        st.stop()
    if not chosen_sites:
        st.error("Pick at least one rating site.")
        st.stop()
    criteria = Criteria(
        sites=chosen_sites,
        min_rating=min_rating,
        per_site_min=per_site,
        hotel_classes=set(classes),
        include_unknown_class=include_unknown_class,
        min_reviews=int(min_reviews),
        missing_policy=missing,
    )
    bar = st.progress(0.0, text="Starting…")
    try:
        discovery, sources = build_sources(live, chosen_sites, max_items=max(150, max_hotels * 2))
        result = pipeline.run(
            area,
            discovery,
            sources,
            criteria,
            all_inclusive=all_inclusive,
            max_hotels=max_hotels,
            discovery_options={"check_in": check_in, "adults": int(adults)},
            status=lambda msg, frac: bar.progress(min(max(frac, 0.0), 1.0), text=msg),
        )
    except SourceError as exc:
        bar.empty()
        st.error(str(exc))
        st.stop()
    bar.empty()
    st.session_state["result"] = (result, chosen_sites, area)

if "result" in st.session_state:
    result, sites, searched_area = st.session_state["result"]
    for warning in result.warnings:
        st.warning(warning)

    c1, c2, c3 = st.columns(3)
    c1.metric("Hotels found", result.discovered)
    c2.metric("Meet all criteria", len(result.passed))
    c3.metric("Excluded", len(result.excluded))

    st.subheader(f"✅ Resorts in {searched_area} that meet your criteria")
    if result.passed:
        df = hotels_table(result.passed, sites)
        st.dataframe(df, column_config=link_columns(df), hide_index=True, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False), f"resorts_{searched_area}.csv", "text/csv")
        points = pd.DataFrame(
            [{"lat": h.latitude, "lon": h.longitude} for h in result.passed if h.has_coordinates]
        )
        if not points.empty:
            st.map(points, size=60)
    else:
        st.write("No hotel meets every criterion. Try a lower minimum, more hotel classes, "
                 "or *Judge it on the other sites* under More options.")

    with st.expander(f"❌ Excluded hotels ({len(result.excluded)}) and why"):
        if result.excluded:
            hotels, reasons = zip(*result.excluded)
            df = hotels_table(list(hotels), sites, reasons=list(reasons))
            st.dataframe(df, column_config=link_columns(df), hide_index=True, use_container_width=True)

    st.caption("Ratings on Booking.com and Expedia (out of 10) are shown divided by 2. "
               "Hotels are matched across sites by name and location; check the links if a match looks wrong.")
