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
