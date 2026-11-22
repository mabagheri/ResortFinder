from resortfinder.filters import MISSING_EXCLUDE, MISSING_IGNORE, Criteria, evaluate
from resortfinder.models import BOOKING, GOOGLE, TRIPADVISOR, Hotel, SiteRating


def hotel(cls=5, **ratings):
    h = Hotel(name="H", key="h", hotel_class=cls)
    for site, (raw, scale, reviews) in ratings.items():
        h.ratings[site] = SiteRating.from_raw(site, raw, scale, reviews=reviews)
    return h


SITES = [GOOGLE, TRIPADVISOR, BOOKING]


def test_booking_score_out_of_10_is_normalized():
    assert SiteRating.from_raw(BOOKING, 9.2, 10).rating == 4.6


def test_passes_when_every_site_meets_minimum():
    h = hotel(google=(4.6, 5, 1000), tripadvisor=(4.5, 5, 900), booking=(9.0, 10, 500))
    assert evaluate(h, Criteria(sites=SITES, min_rating=4.5)) == []


def test_fails_when_one_site_is_low():
    h = hotel(google=(4.6, 5, 1000), tripadvisor=(4.0, 5, 900), booking=(9.4, 10, 500))
    reasons = evaluate(h, Criteria(sites=SITES, min_rating=4.5))
    assert len(reasons) == 1 and "TripAdvisor" in reasons[0]


def test_hotel_class_filter():
    h = hotel(cls=3, google=(4.9, 5, 1000), tripadvisor=(5, 5, 900), booking=(9.8, 10, 500))
    assert evaluate(h, Criteria(sites=SITES, hotel_classes={4, 5}))
    assert evaluate(h, Criteria(sites=SITES, hotel_classes={3})) == []


def test_unknown_class():
    h = hotel(cls=None, google=(4.9, 5, 1000))
    assert evaluate(h, Criteria(sites=[GOOGLE]))
    assert evaluate(h, Criteria(sites=[GOOGLE], include_unknown_class=True)) == []


def test_missing_site_policy():
    h = hotel(google=(4.8, 5, 1000), tripadvisor=(4.5, 5, 900))  # not on Booking
    assert evaluate(h, Criteria(sites=SITES, missing_policy=MISSING_EXCLUDE)) == ["not found on Booking.com"]
    assert evaluate(h, Criteria(sites=SITES, missing_policy=MISSING_IGNORE)) == []


def test_min_reviews():
    h = hotel(google=(5.0, 5, 12))
    assert evaluate(h, Criteria(sites=[GOOGLE], min_reviews=50))
    assert evaluate(h, Criteria(sites=[GOOGLE], min_reviews=10)) == []


def test_per_site_minimum():
    h = hotel(google=(4.3, 5, 1000), tripadvisor=(4.5, 5, 900))
    c = Criteria(sites=[GOOGLE, TRIPADVISOR], min_rating=4.5, per_site_min={GOOGLE: 4.2})
    assert evaluate(h, c) == []
