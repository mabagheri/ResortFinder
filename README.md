# ResortFinder 🏝️

A Streamlit app that finds the hotels and all-inclusive resorts in an area (e.g. Cancun) and keeps
only those that:

- have a **hotel class** you choose (2 to 5 stars), and
- have at least your **minimum rating** (e.g. 4.5/5) on **Google Maps, TripAdvisor, Booking.com and Expedia**.

Feature 2 (cheapest m-night stay in a date range) is planned; see
[docs/REFERENCE_REPOS.md](docs/REFERENCE_REPOS.md).

## How it works

1. **Collect an area once (uses APIs).** The first time you search an area, the app collects
   **every** hotel there (all classes, all ratings) from Google Hotels, looks each one up on the other
   sites, and saves everything to `data/areas/<area>__<all-inclusive|all-hotels>.csv`.
2. **Filter for free.** Hotel class, minimum rating, per-site minimums, minimum review count, and how to
   treat hotels missing from a site are applied to the saved file, so results update instantly and use
   no API calls. Ratings may be a little old, which is fine for choosing a resort.
3. **Update when you want.** *Fetch missing sites* adds only a site the file doesn't have yet (e.g.
   after you add a new key). *Refresh from the web* collects the area again.

Details:
- The same hotel is matched across sites by **name words and GPS distance**. Sister hotels such as
  "Hyatt Ziva" and "Hyatt Zilara" are kept apart.
- Booking.com and Expedia scores out of 10 are divided by 2 (9.0/10 = 4.5/5).
- The file records the date each site was checked, so "not found on Booking.com" is different from
  "Booking.com not checked yet".
- Results have links to every site (to verify a match), a list of excluded hotels with the reason,
  CSV download and a map. Area files can be downloaded as CSV/Excel and uploaded again.

## What it costs (nothing, with free tiers)

| Site | Source | Key (Streamlit secret) | Free tier | Needed? |
|---|---|---|---|---|
| Hotel list, class, Google rating | SerpApi Google Hotels | `SERPAPI_KEY` | 250 searches/month, no card | **Yes**, the only required key |
| TripAdvisor | Apify `maxcopell/tripadvisor` | `APIFY_TOKEN` | $5 credit/month, no card | Recommended |
| Booking.com | Apify `voyager/booking-scraper` | `APIFY_TOKEN` (same) | same $5 credit | Recommended |
| TripAdvisor (alternative) | [TripAdvisor Content API](https://www.tripadvisor.com/developers) | `TRIPADVISOR_API_KEY` | 5,000 calls/month; asks for a card | Optional; used instead of Apify if set |
| Expedia | an Apify Expedia scraper of your choice | `APIFY_TOKEN` + `EXPEDIA_APIFY_ACTOR` | same $5 credit | Optional |
| Google Maps (exact) | Google Places API | `GOOGLE_PLACES_API_KEY` | free monthly quota; needs a billing account | Not needed: Google Hotels already gives the Google rating |
| Permanent storage of area files | GitHub | `GITHUB_TOKEN` + `GITHUB_REPO` | free | Recommended on Streamlit Cloud |

With `SERPAPI_KEY` + `APIFY_TOKEN` you get **Google, TripAdvisor and Booking.com** ratings for free.
Collecting one area of 100 hotels uses about 5 SerpApi searches and one Apify scraper run per site. Thanks to the saved files, that happens once per area, not once per search.

A site with no key is skipped. With **no keys at all** the app runs on **fictional demo data**.

> Booking.com and Expedia have no public ratings API, so third-party scrapers are used. Their output
> fields can change; the actor and its input can be swapped in secrets without code changes (see
> `.streamlit/secrets.toml.example`). Using scrapers may conflict with those sites' terms of use.

## Where the saved files live

Streamlit Community Cloud **deletes files the app writes whenever it restarts or sleeps**. Three ways
to keep your area files:

1. **GitHub (recommended, automatic):** add `GITHUB_TOKEN` and `GITHUB_REPO` to the secrets. Each saved
   area is committed to the `resort-data` branch of that repo and loaded from there after a restart.
   Use a fine-grained token limited to this one repository with "Contents: Read and write".
2. **Download / upload:** in the app, *Saved area files* → download CSV or Excel, and upload it later.
3. **Commit them yourself:** put CSV files in `data/areas/` of the deployed branch.

## Run on Streamlit Community Cloud

1. Push this repo to GitHub (already done if you are reading this there).
2. Go to [share.streamlit.io](https://share.streamlit.io), click **Create app**, choose this repo,
   branch, and main file `streamlit_app.py`.
3. In **Advanced settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example`
   with your keys filled in (only `SERPAPI_KEY` is required; add `GITHUB_TOKEN`/`GITHUB_REPO` to keep
   saved areas). Secrets can also be changed later in the app's **Settings**.
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
  pipeline.py               collect (APIs, once per area) / apply_filters (free)
  store.py                  area files: CSV/Excel, local folder + GitHub copy
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
