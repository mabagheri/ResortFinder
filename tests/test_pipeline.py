from resortfinder import pipeline
from resortfinder.filters import MISSING_IGNORE, Criteria
from resortfinder.http import SourceError
from resortfinder.models import ALL_SITES, BOOKING, GOOGLE, TRIPADVISOR
from resortfinder.sources.base import RatingSource
from resortfinder.sources.demo import DemoDiscovery, DemoRatingSource


def demo_sources(sites=ALL_SITES):
    return {s: DemoRatingSource(s) for s in sites if s != GOOGLE}


def collect(**kw):
    hotels, warnings = pipeline.collect("Cancun", DemoDiscovery(), kw.pop("sources", demo_sources()), **kw)
    return hotels, warnings


def test_collect_gets_every_class_and_marks_checked_sites():
    hotels, warnings = collect()
    assert not warnings
    assert {h.hotel_class for h in hotels} >= {4, 5}
    assert all(set(h.checked) == set(ALL_SITES) for h in hotels)


def test_filtering_saved_hotels_meets_criteria():
    hotels, _ = collect()
    res = pipeline.apply_filters(hotels, Criteria(sites=ALL_SITES, min_rating=4.3, hotel_classes={4, 5}))
    assert res.discovered == len(res.passed) + len(res.excluded)
    for h in res.passed:
        assert h.hotel_class in {4, 5}
        assert all(h.ratings[s].rating >= 4.3 for s in ALL_SITES)


def test_lower_threshold_never_passes_fewer_hotels():
    hotels, _ = collect()
    strict = pipeline.apply_filters(hotels, Criteria(sites=ALL_SITES, min_rating=4.6))
    loose = pipeline.apply_filters(hotels, Criteria(sites=ALL_SITES, min_rating=4.0))
    ignore = pipeline.apply_filters(hotels, Criteria(sites=ALL_SITES, min_rating=4.0, missing_policy=MISSING_IGNORE))
    assert len(strict.passed) <= len(loose.passed) <= len(ignore.passed)


def test_unchecked_site_is_skipped_with_warning_then_fetched_later():
    hotels, _ = collect(sources=demo_sources([TRIPADVISOR]))
    res = pipeline.apply_filters(hotels, Criteria(sites=[GOOGLE, TRIPADVISOR, BOOKING], min_rating=4.0))
    assert res.sites_used == [GOOGLE, TRIPADVISOR] and "Booking.com" in res.warnings[0]

    class Fail(RatingSource):
        def rate(self, area, hotels, progress=None):
            raise AssertionError("discovery/other sites must not be called again")

    hotels2, _ = pipeline.collect("Cancun", Fail(), {BOOKING: DemoRatingSource(BOOKING), TRIPADVISOR: Fail()},
                                  existing=hotels, only_sites=[BOOKING])
    assert all(BOOKING in h.checked for h in hotels2)


class Broken(RatingSource):
    site = TRIPADVISOR

    def rate(self, area, hotels, progress=None):
        raise SourceError("TripAdvisor: HTTP 401 bad key")


def test_failed_source_becomes_warning_and_is_not_marked_checked():
    hotels, warnings = collect(sources={TRIPADVISOR: Broken()})
    assert warnings and "TripAdvisor" in warnings[0]
    assert not any(TRIPADVISOR in h.checked for h in hotels)
