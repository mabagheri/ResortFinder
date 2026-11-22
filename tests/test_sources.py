import json
from pathlib import Path

from resortfinder.models import BOOKING, GOOGLE
from resortfinder.sources.apify import _fill, coords, parse_item
from resortfinder.sources.google_hotels import parse_property, serpapi_rating_filter

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_google_hotels.json"


def test_parse_serpapi_properties():
    items = json.loads(FIXTURE.read_text())["properties"]
    hotels = [h for h in (parse_property(i, "USD") for i in items) if h]
    assert [h.name for h in hotels] == ["Sample Grand Resort", "Sample Budget Inn"]  # rental skipped
    grand, inn = hotels
    assert grand.hotel_class == 5 and grand.ratings[GOOGLE].rating == 4.7
    assert grand.ratings[GOOGLE].reviews == 3210 and grand.price_per_night == 512
    assert grand.is_all_inclusive is True
    assert inn.hotel_class == 3  # parsed from "3-star hotel"


def test_serpapi_rating_filter():
    assert serpapi_rating_filter(4.6) == "9"
    assert serpapi_rating_filter(4.2) == "8"
    assert serpapi_rating_filter(3.0) is None


def test_apify_item_parsing_handles_common_shapes():
    item = {"name": "X", "rating": 9.2, "reviews": 1534, "url": "u", "location": {"lat": "21.1", "lng": "-86.7"}}
    r = parse_item(BOOKING, item, 10)
    assert r.rating == 4.6 and r.reviews == 1534 and r.url == "u"
    assert coords(item) == (21.1, -86.7)
    assert parse_item(BOOKING, {"name": "Y", "reviewScore": {"score": "8,8"}}, 10).rating == 4.4
    assert parse_item(BOOKING, {"name": "Z"}, 10) is None


def test_actor_input_placeholders():
    out = _fill({"search": "{area}", "maxItems": "{max_items}", "q": "hotels in {area}"}, {"area": "Cancun", "max_items": 50})
    assert out == {"search": "Cancun", "maxItems": 50, "q": "hotels in Cancun"}


class _Resp:
    def __init__(self, body, status=200):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class _FakeApify:
    """Run starts RUNNING, finishes on the first poll; dataset returns `items`."""

    def __init__(self, items, final="SUCCEEDED"):
        self.items, self.final, self.calls, self.headers = items, final, [], {}

    def post(self, url, params=None, json=None, timeout=None):
        self.calls.append(("start", url, json))
        return _Resp({"data": {"id": "r1", "status": "RUNNING", "defaultDatasetId": "d1"}})

    def get(self, url, params=None, timeout=None):
        self.calls.append(("get", url, None))
        if "/actor-runs/" in url:
            return _Resp({"data": {"id": "r1", "status": self.final, "defaultDatasetId": "d1"}})
        return _Resp(self.items)


def _apify_source(site, items, **kw):
    from resortfinder.sources.apify import ApifySource
    src = ApifySource(site, "token", **kw)
    src.session = _FakeApify(items, kw.pop("final", "SUCCEEDED")) if "final" not in kw else src.session
    return src


def test_tripadvisor_via_apify_matches_hotels_and_reads_5_scale():
    from resortfinder.models import TRIPADVISOR, Hotel
    items = [{"name": "Sample Grand Resort - All Inclusive", "rating": 4.5, "numberOfReviews": 2100,
              "webUrl": "https://ta/1", "latitude": 21.1001, "longitude": -86.7601},
             {"name": "Other Place", "rating": 3.0, "latitude": 21.2, "longitude": -86.8}]
    src = _apify_source(TRIPADVISOR, items)
    hotels = [Hotel(name="Sample Grand Resort", key="k", latitude=21.1, longitude=-86.76),
              Hotel(name="Not Listed Hotel", key="n", latitude=21.0, longitude=-86.7)]
    out = src.rate("Cancun", hotels)
    assert out["k"].rating == 4.5 and out["k"].reviews == 2100 and out["k"].url == "https://ta/1"
    assert out["n"] is None
    start = src.session.calls[0]
    assert start[1].endswith("/acts/maxcopell~tripadvisor/runs") and start[2]["query"] == "Cancun"
    assert start[2]["includeHotels"] is True and isinstance(start[2]["maxItemsPerQuery"], int)


def test_apify_unreadable_output_gives_clear_error_and_is_not_cached():
    import pytest
    from resortfinder.http import SourceError
    from resortfinder.models import BOOKING, Hotel
    src = _apify_source(BOOKING, [{"title": "X", "stars": 5}])
    with pytest.raises(SourceError, match="Fields received: stars, title"):
        src.rate("Cancun", [Hotel(name="X", key="x")])
    src.session.items = []
    with pytest.raises(SourceError, match="returned no results"):
        src.rate("Cancun", [Hotel(name="X", key="x")])


def test_apify_failed_run_raises():
    import pytest
    from resortfinder.http import SourceError
    from resortfinder.models import BOOKING, Hotel
    from resortfinder.sources.apify import ApifySource
    src = ApifySource(BOOKING, "token")
    src.session = _FakeApify([], final="FAILED")
    with pytest.raises(SourceError, match="status FAILED"):
        src.rate("Cancun", [Hotel(name="X", key="x")])
