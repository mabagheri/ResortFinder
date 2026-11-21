# Reference Repositories for ResortFinder

A list of existing open-source projects to learn from (or reuse) while building ResortFinder.
Star counts and "last push" dates were checked on 2026-11-21. Read each repo's license
before copying code. Scraping can break the sites' Terms of Service: prefer official APIs where they exist.

ResortFinder has two features:

1. **Rating filter**: find every hotel/all-inclusive resort in an area (e.g. Cancun) whose rating is at
   least X (e.g. 4.5/5) on **Expedia, TripAdvisor, Booking.com and Google Maps**.
2. **Cheapest stay window**: for a time period (e.g. two months), try every m-night window (e.g. every
   possible 4-night stay), get prices from several sites, and return the cheapest window per hotel.

---

## Key design insight: Google Hotels already does much of this

Google Hotels (google.com/travel/hotels) shows, for one hotel and one date range, **prices from many
OTAs at once** (Booking, Expedia, Hotels.com, the hotel's own site, etc.), and its "Reviews" tab shows
**ratings from other sites** (TripAdvisor, Expedia, Booking...). One Google Hotels client could give
you a big part of both features. The best repos for this are marked ⭐ below.

---

## Feature 1: Hotel discovery + multi-site rating filter

### Google Maps / Google ratings
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) | 8.3k | Go | Most popular Google Maps scraper. Query like `all inclusive resort in Cancun` → name, address, rating, review count, coordinates. CLI, Web UI, REST API, Docker. Good for **discovering the hotel list** of an area. |
| [gaspa93/googlemaps-scraper](https://github.com/gaspa93/googlemaps-scraper) | 537 | Python | Google Maps reviews/ratings for a list of place URLs. |
| [georgekhananaev/google-reviews-scraper-pro](https://github.com/georgekhananaev/google-reviews-scraper-pro) | 350 | Python | Maintained Google reviews scraper (2026). |
| [w-e-ll/Google-Maps-Hotel-Async-Python-Scraper](https://github.com/w-e-ll/Google-Maps-Hotel-Async-Python-Scraper) | 11 | Python | Small async example focused on hotels. |

Official alternative: **Google Places API** (`rating`, `user_ratings_total`), paid per request but stable.

### TripAdvisor
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| [omkarcloud/tripadvisor-scraper](https://github.com/omkarcloud/tripadvisor-scraper) | 213 | Python | Hotels with ratings, rankings, prices, details. Actively maintained. |
| [algo7/TripAdvisor-Review-Scraper](https://github.com/algo7/TripAdvisor-Review-Scraper) | 30 | Go | Maintained (Nov 2026) review/rating scraper. |
| [andorfermichael/tripadvisor-scraper](https://github.com/andorfermichael/tripadvisor-scraper) | 36 | – | "Scrape the hotel reviews of a whole city": the same city-wide idea as Feature 1 (old). |

Official alternative: **TripAdvisor Content API** (location search + rating; free tier available).

### Booking.com
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| [ZoranPandovski/BookingScraper](https://github.com/ZoranPandovski/BookingScraper) | 100 | Python | Classic Booking.com search scraper (name, score, price). |
| [scrapehero-code/booking-hotel-scraper](https://github.com/scrapehero-code/booking-hotel-scraper) | 35 | Python | Simple, readable reference: name, price, rating, location (old, selectors may be stale). |
| [sudoknight/booking-reviews-scraper](https://github.com/sudoknight/booking-reviews-scraper) | 28 | Python | Booking.com reviews/score. |
| [gkzz/deephotel](https://github.com/gkzz/deephotel) | 17 | Python | Scrapy project scraping **both TripAdvisor and Booking.com**: an example of a multi-source pipeline. |

Note: Booking.com scores are out of **10**, the others out of 5. Normalize (score/2) before applying the 4.5 threshold.

### Expedia
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| [factden/expedia-hotel-reviews-scraper](https://github.com/factden/expedia-hotel-reviews-scraper) | 4 | – | Expedia Group (Expedia, Hotels.com, Vrbo...) guest ratings + sub-ratings (Apify actor). |
| [omkarcloud/hotels-com-scraper](https://github.com/omkarcloud/hotels-com-scraper) | 1 | Python | Hotels.com shares Expedia's review system, so its rating is effectively the Expedia rating. |

Expedia has few good open-source scrapers. Consider getting the Expedia rating from Google Hotels' reviews tab or from a scraping API (see "Multi-site toolkits").

### Multi-site toolkits (all features)
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| ⭐ [scrapfly/scrapfly-scrapers](https://github.com/scrapfly/scrapfly-scrapers) | 1.1k | Python | Maintained, nightly-tested scrapers incl. **bookingcom, expedia, tripadvisor, google, kayak, marriott, airbnb**. Same structure for every site: a good **pattern for a pluggable "source" interface**. Has an `llms.txt` written for AI agents. Needs a Scrapfly key, but the parsing logic is reusable. |

---

## Feature 2: Cheapest m-night window in a date range

### Multi-OTA price comparison
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| ⭐ [gobeyondpty/swoop-hotels](https://github.com/gobeyondpty/swoop-hotels) | 4 | Python | `pip install swoop-hotels`. Google Hotels without an API key: `hotels(query, check_in, check_out)`, `hotel_prices(token, ...)` (**prices per provider**), `hotel_reviews(token)`. Close to the core engine you need. |
| ⭐ [vecyang1/google-hotels-cli](https://github.com/vecyang1/google-hotels-cli) | 1 | Python | Google Hotels CLI/MCP: free `batchexecute` client with **SerpAPI fallback**, `--min-rating`, star/amenity filters, a 2-hour cache, and JSON/CSV export. Good example of a provider-fallback design and caching. |
| [seanbabalala/hotelrate-crawl](https://github.com/seanbabalala/hotelrate-crawl) | 14 | Python | Compares **Trip.com, Booking.com, Agoda, Google Hotels in parallel** with Playwright and normalizes the results. Has a demo mode with fake data (useful for tests). Good architecture reference for the multi-site part. |
| [MikkoParkkola/trvl](https://github.com/MikkoParkkola/trvl) | 95 | Go | Travel MCP server/CLI: hotels from 6 sources, merge and de-duplicate, price watches. Its docs on "list price vs verified price" are worth reading. |
| [affromero/flight-finder](https://github.com/affromero/flight-finder) | 189 | – | Self-hosted flight/**hotel** price tracking with price history and alerts. Reference for storing prices over time and scheduling. |
| [borski/travel-hacking-toolkit](https://github.com/borski/travel-hacking-toolkit) | 1k | – | Agent skills + MCP servers, incl. **Trivago MCP** (free hotel metasearch) and a `compare-hotels` skill. |

### Date-window / flexible-date search patterns (from flights, same algorithm)
| Repo | ★ | Lang | Why it is useful |
|---|---|---|---|
| [AWeirdDev/flights](https://github.com/AWeirdDev/flights) (`fast-flights`) | 2.1k | Python | Reverse-engineered Google Travel (protobuf). The same approach (Google's `TravelFrontendUi`) powers swoop-hotels. |
| [n-patel/flights](https://github.com/n-patel/flights) | 43 | Python | Keeps computing the cheapest trip **when your dates are flexible** and notifies you: the Feature 2 loop. |
| [cohaolain/ryanair-py](https://github.com/cohaolain/ryanair-py) | 70 | Python | Clean API for "cheapest within a date range". |
| [brendanteske/hotelAvailability](https://github.com/brendanteske/hotelAvailability) | 0 | – | Playwright scraper tracking **several hotels across flexible dates** with Discord alerts: small, close to Feature 2. |
| [Mohammed-Shehsin/booking-price-tracker](https://github.com/Mohammed-Shehsin/booking-price-tracker) | 1 | Python | Playwright scraper for **daily Booking.com room prices** over a period. |

### Paid / official APIs worth considering (more stable than scraping)
- **SerpApi Google Hotels engine**: prices per OTA plus ratings for a date range, as JSON.
- **Xotelo** (free, TripAdvisor-based hotel prices from several OTAs); example client: [wolfiesch/flightfinder](https://github.com/wolfiesch/flightfinder).
- **Makcorps hotel price API**; example: [camburley/hotel-deal-finder](https://github.com/camburley/hotel-deal-finder).
- **Amadeus Self-Service Hotel APIs**; example: [amadeus4dev/amadeus-hotel-booking-django](https://github.com/amadeus4dev/amadeus-hotel-booking-django).
- **Booking.com Demand API / Expedia Rapid API**: official, but need affiliate/partner approval.

---

## Suggested architecture (based on the above)

```
resortfinder/
  sources/            # one adapter per site, same interface (pattern from scrapfly-scrapers)
    google_hotels.py  # discovery + multi-OTA prices + ratings (swoop-hotels / SerpApi)
    google_maps.py    # rating (gosom scraper or Places API)
    tripadvisor.py    # rating (Content API or omkarcloud scraper)
    booking.py        # rating (/10 → /5) + price
    expedia.py        # rating + price
  match.py            # match the same hotel across sites (name + lat/lng distance)
  feature1_filter.py  # keep hotels where every site's rating >= threshold
  feature2_windows.py # for start in range(period): price(start, start+m) per source → min
  cache.py            # cache (hotel, check_in, nights, source) → price
```

Notes for Feature 2:
- In a 60-day period with m=4 there are 57 windows. For N hotels × S sites that is N×S×57 requests,
  so cache results, rate-limit, and filter with Feature 1 first.
- Cheaper method: fetch **one-night prices** for every date, add them up for each window
  (a sliding-window sum) to rank the windows, then check only the best few windows with a real
  m-night search (multi-night prices and discounts can differ from the sum of single nights).
- Compare **total price including taxes/fees** for the same room type and board (all-inclusive).
