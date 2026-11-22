from resortfinder import pipeline
from resortfinder.filters import MISSING_IGNORE, Criteria
from resortfinder.http import SourceError
from resortfinder.models import ALL_SITES, GOOGLE, TRIPADVISOR
from resortfinder.sources.base import RatingSource
from resortfinder.sources.demo import DemoDiscovery, DemoRatingSource


def demo_sources():
    return {s: DemoRatingSource(s) for s in ALL_SITES if s != GOOGLE}


def test_demo_pipeline_every_passed_hotel_meets_criteria():
    c = Criteria(sites=ALL_SITES, min_rating=4.3, hotel_classes={4, 5})
    res = pipeline.run("Cancun", DemoDiscovery(), demo_sources(), c)
    assert res.discovered == len(res.passed) + len(res.excluded)
    for h in res.passed:
        assert h.hotel_class in {4, 5}
        for s in ALL_SITES:
            assert h.ratings[s].rating >= 4.3


def test_ignore_policy_passes_at_least_as_many():
    strict = pipeline.run("Cancun", DemoDiscovery(), demo_sources(), Criteria(sites=ALL_SITES, min_rating=4.0))
    loose = pipeline.run("Cancun", DemoDiscovery(), demo_sources(),
                         Criteria(sites=ALL_SITES, min_rating=4.0, missing_policy=MISSING_IGNORE))
    assert len(loose.passed) >= len(strict.passed)


class Broken(RatingSource):
    site = TRIPADVISOR

    def rate(self, area, hotels, progress=None):
        raise SourceError("TripAdvisor: HTTP 401 bad key")


def test_failed_source_becomes_warning_not_crash():
    res = pipeline.run("Cancun", DemoDiscovery(), {TRIPADVISOR: Broken()},
                       Criteria(sites=[GOOGLE, TRIPADVISOR], min_rating=4.0))
    assert res.warnings and "TripAdvisor" in res.warnings[0]
    assert res.passed  # judged on Google only
