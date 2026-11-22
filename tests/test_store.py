import base64
import json

from resortfinder import pipeline
from resortfinder.models import ALL_SITES, GOOGLE
from resortfinder.sources.demo import DemoDiscovery, DemoRatingSource
from resortfinder.store import (
    AreaStore, GitHubStore, LocalStore, area_slug, df_to_hotels, hotels_to_df, read_table, to_excel_bytes,
)


def demo_hotels():
    hotels, _ = pipeline.collect("Cancun", DemoDiscovery(), {s: DemoRatingSource(s) for s in ALL_SITES if s != GOOGLE})
    return hotels


def _norm(value):
    if value is None or (isinstance(value, float) and value != value):
        return None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def as_dicts(hotels):
    """Table values, ignoring dtype noise (None vs NaN, 5 vs 5.0) from the CSV round trip."""
    return [{k: _norm(v) for k, v in row.items()} for row in hotels_to_df(hotels).to_dict("records")]


def test_slug():
    assert area_slug("Cancún, Mexico", True) == "cancun-mexico__all-inclusive"
    assert area_slug("Punta Cana", False) == "punta-cana__all-hotels"


def test_csv_round_trip_keeps_ratings_and_not_found(tmp_path):
    hotels = demo_hotels()
    store = LocalStore(tmp_path)
    store.save("cancun__all-inclusive", hotels)
    back = store.load("cancun__all-inclusive")
    assert as_dicts(back) == as_dicts(hotels)
    # "checked but not found" survives (None rating with a checked date)
    for before, after in zip(hotels, back):
        for site in ALL_SITES:
            assert (before.ratings.get(site) is None) == (after.ratings.get(site) is None)
            assert before.checked.get(site) == after.checked.get(site)
    assert store.list() == ["cancun__all-inclusive"]


def test_excel_round_trip():
    hotels = demo_hotels()
    back = df_to_hotels(read_table(to_excel_bytes(hotels_to_df(hotels)), "x.xlsx"))
    assert [h.name for h in back] == [h.name for h in hotels]
    assert [h.ratings[GOOGLE].rating for h in back] == [h.ratings[GOOGLE].rating for h in hotels]


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)
        self.content = b""

    def json(self):
        return self._body


class FakeGitHub:
    """Minimal in-memory stand-in for the GitHub contents/refs API."""

    def __init__(self):
        self.headers, self.files, self.branches = {}, {}, {"main": "sha-main"}

    def get(self, url, params=None, timeout=None):
        if "/git/ref/heads/" in url:
            name = url.rsplit("/", 1)[1]
            return FakeResp(200, {"object": {"sha": self.branches[name]}}) if name in self.branches else FakeResp(404, {})
        if url.endswith("/repos/me/repo"):
            return FakeResp(200, {"default_branch": "main"})
        path = url.split("/contents/", 1)[1]
        if path in self.files:
            content, sha = self.files[path]
            return FakeResp(200, {"content": base64.b64encode(content).decode(), "sha": sha})
        if path == "data/areas" and self.files:
            return FakeResp(200, [{"name": p.rsplit("/", 1)[1]} for p in self.files])
        return FakeResp(404, {})

    def post(self, url, data=None, timeout=None):
        body = json.loads(data)
        self.branches[body["ref"].rsplit("/", 1)[1]] = body["sha"]
        return FakeResp(201, {})

    def put(self, url, data=None, timeout=None):
        body = json.loads(data)
        path = url.split("/contents/", 1)[1]
        if path in self.files:
            assert body["sha"] == self.files[path][1]
        assert body["branch"] == "resort-data"
        self.files[path] = (base64.b64decode(body["content"]), f"sha{len(self.files)}-{len(body['content'])}")
        return FakeResp(200, {})


def test_github_store_creates_branch_saves_and_reloads(tmp_path):
    gh = FakeGitHub()
    remote = GitHubStore("t", "me/repo", session=gh)
    hotels = demo_hotels()
    AreaStore(LocalStore(tmp_path / "a"), remote).save("cancun__all-inclusive", hotels)
    assert "resort-data" in gh.branches
    # A fresh server (empty local folder) gets the file back from GitHub.
    fresh = AreaStore(LocalStore(tmp_path / "b"), remote)
    assert as_dicts(fresh.load("cancun__all-inclusive")) == as_dicts(hotels)
    assert (tmp_path / "b" / "cancun__all-inclusive.csv").exists()
    remote.save("cancun__all-inclusive", hotels)  # update uses the existing sha
    assert fresh.list() == ["cancun__all-inclusive"]


def test_github_failure_keeps_local_copy(tmp_path):
    class Down(FakeGitHub):
        def put(self, *a, **k):
            return FakeResp(403, {"message": "Resource not accessible"})

    store = AreaStore(LocalStore(tmp_path), GitHubStore("t", "me/repo", session=Down()))
    warning = store.save("x__all-hotels", demo_hotels())
    assert "GitHub copy failed" in warning and "403" in warning
    assert store.local.load("x__all-hotels")
