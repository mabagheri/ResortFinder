# ResortFinder 🏝️

A Streamlit app that finds the hotels and all-inclusive resorts in an area (e.g. Cancun) and keeps
only those that:

- have a **hotel class** you choose (2 to 5 stars), and
- have at least your **minimum rating** (e.g. 4.5/5) on **Google Maps, TripAdvisor, Booking.com and Expedia**.

Feature 2 (cheapest m-night stay in a date range) is planned; see
[docs/REFERENCE_REPOS.md](docs/REFERENCE_REPOS.md).

## How it works

1. **Find hotels**: Google Hotels (through [SerpApi](https://serpapi.com)) lists the hotels of the area,
   with their class, Google rating, position and a price.
2. **Cheap filter first**: hotels that fail on class or Google rating are dropped before any other
   site is called, to save API quota.
3. **Other sites**: each remaining hotel is looked up on TripAdvisor (official Content API) and on
   Booking.com / Expedia (Apify scrapers). The same hotel is matched across sites by **name and GPS
   distance**. Sister hotels such as "Hyatt Ziva" and "Hyatt Zilara" are kept apart.
4. **Decide**: Booking.com and Expedia scores out of 10 are divided by 2. A hotel passes only if every
   selected site meets the minimum. You choose whether a hotel that is *not found* on a site is
   excluded (strict) or judged on the other sites.

The results table has links to every site so you can check each match. Excluded hotels are listed
with the reason, and the results can be downloaded as CSV.

## Data sources and keys

| Site | Source | Key (Streamlit secret) | Free tier | Needed? |
|---|---|---|---|---|
| Hotel list, class, Google rating | SerpApi Google Hotels | `SERPAPI_KEY` | 250 searches/month | **Yes**, for live mode |
| TripAdvisor | [TripAdvisor Content API](https://www.tripadvisor.com/developers) | `TRIPADVISOR_API_KEY` | 5,000 calls/month (2 per hotel) | Optional |
| Booking.com | Apify `voyager/booking-scraper` | `APIFY_TOKEN` | $5 usage/month | Optional |
| Expedia | an Apify Expedia scraper of your choice | `APIFY_TOKEN` + `EXPEDIA_APIFY_ACTOR` | same | Optional |
| Google Maps (exact) | Google Places API | `GOOGLE_PLACES_API_KEY` | pay as you go | Optional (Google Hotels' rating is used otherwise) |

A site with no key is greyed out in the app. With **no keys at all** the app runs on **fictional
demo data**, so you can try the interface right away.

> Booking.com and Expedia have no public ratings API, so third-party scrapers are used. Their output
> fields can change; the actor and its input can be swapped in secrets without code changes (see
> `.streamlit/secrets.toml.example`). Using scrapers may conflict with those sites' terms of use.

## Run on Streamlit Community Cloud

1. Push this repo to GitHub (already done if you are reading this there).
2. Go to [share.streamlit.io](https://share.streamlit.io), click **Create app**, choose this repo,
   branch, and main file `streamlit_app.py`.
3. In **Advanced settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example`
   with your keys filled in. Secrets can also be changed later in the app's **Settings**.
4. Deploy.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add your keys (optional)
streamlit run streamlit_app.py
pytest                                                       # tests use no network
```

## Project layout

```
streamlit_app.py            UI
resortfinder/
  pipeline.py               discover → pre-filter → enrich → filter
  filters.py                the pass/fail rules (class, minimum rating, missing data, review count)
  matching.py               same hotel across sites (name words + GPS distance)
  models.py                 Hotel, SiteRating (everything normalized to /5)
  http.py                   HTTP session with retries, in-memory cache
  sources/
    google_hotels.py        SerpApi Google Hotels (hotel list, class, Google rating)
    google_places.py        Google Places API (optional Google Maps rating)
    tripadvisor.py          TripAdvisor Content API
    apify.py                Booking.com / Expedia through Apify actors
    demo.py                 fictional demo data (data/demo_hotels.json)
tests/                      pytest (offline)
docs/REFERENCE_REPOS.md     related open-source projects
```

To add another site, write a class in `resortfinder/sources/` with a `rate(area, hotels)` method
(or `rate_one(area, hotel)` for one lookup per hotel), then add it in `build_sources()` in
`streamlit_app.py`.
