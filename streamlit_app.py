"""ResortFinder – Feature 1: find hotels in an area that are rated highly on every site.

The first search of an area collects all its hotels and ratings (API calls) and saves them to
data/areas/<area>.csv. After that, changing the criteria only filters the saved file (free).

Run locally:   streamlit run streamlit_app.py
API keys go in .streamlit/secrets.toml (see secrets.toml.example) or in the
"Secrets" box of Streamlit Community Cloud.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import tempfile
from pathlib import Path

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
from resortfinder.store import (
    AreaStore, GitHubStore, LocalStore, area_slug, df_to_hotels, hotels_to_df, read_table,
    summarize, to_excel_bytes,
)

st.set_page_config(page_title="ResortFinder", page_icon="🏝️", layout="wide")


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets.toml at all
        value = None
    return str(value or os.environ.get(name, default)).strip()


@st.cache_resource
def shared_cache() -> TTLCache:
    return TTLCache(ttl_seconds=7 * 24 * 3600)


KEYS = {
    "serpapi": secret("SERPAPI_KEY"),
    "places": secret("GOOGLE_PLACES_API_KEY"),
    "tripadvisor": secret("TRIPADVISOR_API_KEY"),
    "apify": secret("APIFY_TOKEN"),
    "github": secret("GITHUB_TOKEN"),
}
EXPEDIA_ACTOR = secret("EXPEDIA_APIFY_ACTOR")
GITHUB_REPO = secret("GITHUB_REPO")


def site_available(site: str) -> tuple[bool, str]:
    """Whether a site can be fetched live, and which secret is missing if not."""
    if site == GOOGLE:
        return bool(KEYS["serpapi"]), "SERPAPI_KEY"
    if site == TRIPADVISOR:
        return bool(KEYS["tripadvisor"] or KEYS["apify"]), "APIFY_TOKEN (or TRIPADVISOR_API_KEY)"
    if site == BOOKING:
        return bool(KEYS["apify"]), "APIFY_TOKEN"
    if site == EXPEDIA:
        return bool(KEYS["apify"] and EXPEDIA_ACTOR), "APIFY_TOKEN + EXPEDIA_APIFY_ACTOR"
    return False, ""


def build_sources(live: bool, max_items: int):
    """Discovery + every rating source that has a key."""
    cache = shared_cache()
    if not live:
        return DemoDiscovery(), {s: DemoRatingSource(s) for s in ALL_SITES if s != GOOGLE}
    discovery = GoogleHotelsDiscovery(KEYS["serpapi"], cache=cache)
    sources = {}
    if KEYS["places"]:
        sources[GOOGLE] = GooglePlacesSource(KEYS["places"], cache=cache)
    if KEYS["tripadvisor"]:  # official API, if you have a key
        sources[TRIPADVISOR] = TripAdvisorSource(
            KEYS["tripadvisor"], referer=secret("TRIPADVISOR_REFERER") or None, cache=cache
        )
    elif KEYS["apify"]:  # otherwise the free Apify scraper
        sources[TRIPADVISOR] = ApifySource(
            TRIPADVISOR, KEYS["apify"], actor=secret("TRIPADVISOR_APIFY_ACTOR") or None,
            actor_input=secret("TRIPADVISOR_APIFY_INPUT") or None, max_items=max_items, cache=cache,
        )
    if site_available(BOOKING)[0]:
        sources[BOOKING] = ApifySource(
            BOOKING, KEYS["apify"], actor=secret("BOOKING_APIFY_ACTOR") or None,
            actor_input=secret("BOOKING_APIFY_INPUT") or None, max_items=max_items, cache=cache,
        )
    if site_available(EXPEDIA)[0]:
        sources[EXPEDIA] = ApifySource(
            EXPEDIA, KEYS["apify"], actor=EXPEDIA_ACTOR, actor_input=secret("EXPEDIA_APIFY_INPUT") or None,
            scale=float(secret("EXPEDIA_RATING_SCALE", "10")), max_items=max_items, cache=cache,
        )
    return discovery, sources


@st.cache_resource
def get_store(live: bool) -> AreaStore:
    if not live:  # demo data never mixes with real saved areas
        return AreaStore(LocalStore(Path(tempfile.gettempdir()) / "resortfinder-demo"))
    remote = None
    if KEYS["github"] and GITHUB_REPO:
        remote = GitHubStore(KEYS["github"], GITHUB_REPO, branch=secret("GITHUB_BRANCH", "resort-data"))
    return AreaStore(LocalStore(), remote)


def stars(n) -> str:
    return "★" * int(n) if n else "?"


def hotels_table(hotels, sites, reasons=None) -> pd.DataFrame:
    rows = []
    for i, h in enumerate(hotels):
        row = {"Hotel": h.name, "Class": stars(h.hotel_class), "Avg /5": pipeline.average_rating(h, sites)}
        for site in sites:
            r = h.ratings.get(site)
            row[f"{SITE_LABELS[site]} /5"] = r.rating if r else None
            row[f"{SITE_LABELS[site]} reviews"] = r.reviews if r else None
        row["From $/night"] = h.price_per_night
        if reasons is not None:
            row["Why excluded"] = "; ".join(reasons[i])
        row["Google Hotels"] = h.link
        for site in sites:
            r = h.ratings.get(site)
            if site != GOOGLE:
                row[f"{SITE_LABELS[site]} link"] = r.url if r else None
        rows.append(row)
    return pd.DataFrame(rows)


def column_config(df: pd.DataFrame) -> dict:
    config = {}
    for c in df.columns:
        if "link" in c or c == "Google Hotels":
            config[c] = st.column_config.LinkColumn(c, display_text="open")
        elif c.endswith("/5"):
            config[c] = st.column_config.NumberColumn(c, format="%.2f")
        elif c.endswith("$/night"):
            config[c] = st.column_config.NumberColumn(c, format="$%d")
    return config


def estimate_calls(max_hotels: int, sites: list[str]) -> str:
    parts = [f"SerpApi ≈ {math.ceil(max_hotels / 20)} searches"]
    if TRIPADVISOR in sites and KEYS["tripadvisor"]:
        parts.append(f"TripAdvisor ≈ {2 * max_hotels} calls")
    for site in (TRIPADVISOR, BOOKING, EXPEDIA):
        if site == TRIPADVISOR and KEYS["tripadvisor"]:
            continue
        if site in sites:
            parts.append(f"{SITE_LABELS[site]}: 1 Apify run")
    if GOOGLE in sites and KEYS["places"]:
        parts.append(f"Google Places ≈ {max_hotels} calls")
    return ", ".join(parts)


# ---------------------------------------------------------------- sidebar
st.title("🏝️ ResortFinder")
st.caption("Find the hotels of an area that meet your minimum rating on Google Maps, TripAdvisor, "
           "Booking.com and Expedia.")

with st.sidebar:
    st.header("Area")
    live_possible = bool(KEYS["serpapi"])
    mode = st.radio("Data", ["Live", "Demo (fictional data)"], index=0 if live_possible else 1,
                    disabled=not live_possible, help="Live mode needs at least SERPAPI_KEY in the app secrets.")
    live = mode == "Live"
    area = st.text_input("Area", value="Cancun", help="City or region, e.g. Cancun, Riviera Maya, Punta Cana")
    all_inclusive = st.toggle("All-inclusive resorts only", value=True,
                              help="Each choice is saved as its own file for the area.")

    st.header("Filters (free, instant)")
    classes = st.multiselect("Hotel class", [2, 3, 4, 5], default=[4, 5], format_func=lambda n: f"{n} stars {stars(n)}")
    include_unknown_class = st.checkbox("Include hotels without a class", value=False)
    min_rating = st.slider("Minimum rating (out of 5)", 3.0, 5.0, 4.5, 0.1,
                           help="Booking.com and Expedia scores are out of 10; they are divided by 2 (9.0/10 = 4.5/5).")
    chosen_sites = [s for s in ALL_SITES if st.checkbox(SITE_LABELS[s], value=True)]

    with st.expander("More filter options"):
        per_site = {}
        if st.checkbox("Different minimum per site"):
            for site in chosen_sites:
                per_site[site] = st.number_input(f"{SITE_LABELS[site]} minimum /5", 0.0, 5.0, min_rating, 0.1)
        missing = st.radio(
            "If a hotel is not found on a site", [MISSING_EXCLUDE, MISSING_IGNORE],
            format_func={MISSING_EXCLUDE: "Exclude it (strict)", MISSING_IGNORE: "Judge it on the other sites"}.get,
        )
        min_reviews = st.number_input("Ignore ratings with fewer reviews than", 0, 5000, 50, 10)

    with st.expander("Data collection (uses API calls)"):
        max_hotels = st.slider("Max hotels to collect per area", 20, 200, 100, 20)
        check_in = st.date_input("Sample check-in date", dt.date.today() + dt.timedelta(days=30),
                                 help="Google Hotels needs dates to search; ratings don't depend on them.")
        adults = st.number_input("Adults", 1, 8, 2)

store = get_store(live)
slug = area_slug(area, all_inclusive)
scope_label = "all-inclusive resorts" if all_inclusive else "all hotels"
live_sites = [s for s in ALL_SITES if (site_available(s)[0] if live else True)]

if not live_possible:
    st.info("No API keys found, so the app is running on **fictional demo data**. "
            "Add keys in the app's secrets (see the README) to search real hotels.", icon="ℹ️")

# ---------------------------------------------------------------- load saved data (once per area)
loaded = st.session_state.setdefault("loaded", {})  # slug -> hotels or None
data_key = f"{'live' if live else 'demo'}:{slug}"
if data_key not in loaded:
    try:
        loaded[data_key] = store.load(slug)
    except SourceError as exc:
        st.warning(str(exc))
        loaded[data_key] = None
hotels = loaded[data_key]


def run_collect(existing=None, only_sites=None) -> None:
    bar = st.progress(0.0, text="Starting…")
    try:
        discovery, sources = build_sources(live, max_items=max(150, max_hotels * 2))
        collected, warnings = pipeline.collect(
            area, discovery, sources, all_inclusive=all_inclusive, max_hotels=max_hotels,
            discovery_options={"check_in": check_in, "adults": int(adults)},
            existing=existing, only_sites=only_sites,
            status=lambda msg, frac: bar.progress(min(max(frac, 0.0), 1.0), text=msg),
        )
    except SourceError as exc:
        bar.empty()
        st.error(str(exc))
        return
    bar.empty()
    save_warning = store.save(slug, collected)
    loaded[data_key] = collected
    st.session_state["messages"] = warnings + ([save_warning] if save_warning else [])
    st.rerun()


# ---------------------------------------------------------------- saved-data panel
with st.container(border=True):
    if hotels is None:
        st.markdown(f"**No saved data for {area} ({scope_label}) yet.**")
        st.caption("The first search collects every hotel of the area with all its ratings and saves it, "
                   f"so later filter changes are free. Expected use: {estimate_calls(max_hotels, live_sites)}.")
        if st.button(f"Collect hotels in {area}", type="primary"):
            run_collect()
    else:
        info = summarize(hotels)
        missing_sites = [s for s in live_sites if s not in info.sites_checked]
        st.markdown(
            f"📁 **Saved data for {area} ({scope_label})**: {info.hotels} hotels · "
            f"sites: {', '.join(SITE_LABELS[s] for s in info.sites_checked) or 'none'} · "
            f"last updated {info.last_checked or 'unknown'}"
        )
        cols = iter(st.columns([1, 1, 2]))
        if missing_sites and next(cols).button(
            "Fetch missing sites", help="Adds " + ", ".join(SITE_LABELS[s] for s in missing_sites)
        ):
            run_collect(existing=hotels, only_sites=missing_sites)
        if next(cols).button("Refresh from the web",
                             help=f"Collects everything again: {estimate_calls(max_hotels, live_sites)}"):
            run_collect()

if live:
    not_set = [f"**{SITE_LABELS[s]}** (add {site_available(s)[1]})" for s in ALL_SITES if not site_available(s)[0]]
    if not_set:
        st.info("These sites can't be fetched until their key is in the app's Secrets: " + "; ".join(not_set)
                + ". After adding a key, click **Fetch missing sites**.", icon="🔑")

for message in st.session_state.pop("messages", []):
    st.warning(message)

# ---------------------------------------------------------------- results (filtering only)
if hotels is not None:
    if not classes and not include_unknown_class:
        st.error("Pick at least one hotel class.")
        st.stop()
    criteria = Criteria(
        sites=chosen_sites, min_rating=min_rating, per_site_min=per_site, hotel_classes=set(classes),
        include_unknown_class=include_unknown_class, min_reviews=int(min_reviews), missing_policy=missing,
    )
    result = pipeline.apply_filters(hotels, criteria)
    for warning in result.warnings:
        st.info(warning)

    c1, c2, c3 = st.columns(3)
    c1.metric("Hotels saved", result.discovered)
    c2.metric("Meet all criteria", len(result.passed))
    c3.metric("Excluded", len(result.excluded))

    st.subheader(f"✅ {scope_label.capitalize()} in {area} that meet your criteria")
    if result.passed:
        df = hotels_table(result.passed, result.sites_used)
        st.dataframe(df, column_config=column_config(df), hide_index=True, use_container_width=True)
        st.download_button("Download these results (CSV)", df.to_csv(index=False), f"results_{slug}.csv", "text/csv")
        points = pd.DataFrame([{"lat": h.latitude, "lon": h.longitude} for h in result.passed if h.has_coordinates])
        if not points.empty:
            st.map(points, size=60)
    else:
        st.write("No hotel meets every criterion. Try a lower minimum, more hotel classes, "
                 "or *Judge it on the other sites* under More filter options.")

    with st.expander(f"❌ Excluded hotels ({len(result.excluded)}) and why"):
        if result.excluded:
            excluded_hotels, reasons = zip(*result.excluded)
            df = hotels_table(list(excluded_hotels), result.sites_used, reasons=list(reasons))
            st.dataframe(df, column_config=column_config(df), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- file management
with st.expander("💾 Saved area files: download / upload"):
    if not live:
        st.caption("Demo mode: files are kept apart from real data.")
    elif store.remote:
        st.caption(f"Files are kept permanently in GitHub: `{GITHUB_REPO}`, branch `{store.remote.branch}`.")
    else:
        st.caption("⚠️ Streamlit Community Cloud deletes files written by the app when it restarts. "
                   "Download your area files, or add GITHUB_TOKEN + GITHUB_REPO to the secrets to keep them "
                   "permanently (see README).")
    if hotels is not None:
        full = hotels_to_df(hotels)
        d1, d2, _ = st.columns([1, 1, 2])
        d1.download_button("Download area file (CSV)", full.to_csv(index=False), f"{slug}.csv", "text/csv")
        d2.download_button("Download area file (Excel)", to_excel_bytes(full), f"{slug}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    uploaded = st.file_uploader(f"Upload a saved file for {area} ({scope_label})", type=["csv", "xlsx"])
    if uploaded is not None and st.button("Use this file"):
        try:
            imported = df_to_hotels(read_table(uploaded.getvalue(), uploaded.name))
        except Exception as exc:  # bad file format
            st.error(f"Could not read the file: {exc}")
        else:
            warning = store.save(slug, imported)
            loaded[data_key] = imported
            st.session_state["messages"] = [warning] if warning else []
            st.rerun()
    saved = store.list()
    if saved:
        st.caption("Saved areas: " + ", ".join(s.replace("__", " · ") for s in saved))

st.caption("Booking.com and Expedia ratings (out of 10) are shown divided by 2. Hotels are matched across "
           "sites by name and location; check the links if a match looks wrong.")
