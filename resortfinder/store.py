"""Save every hotel of an area (with all its ratings) to a CSV file, and load it back.

The first search of an area collects ALL hotels (every class, every rating). Later searches
of that area only filter the saved file, so changing the minimum rating or the hotel classes
costs no API calls.

Files live in data/areas/. Streamlit Community Cloud deletes files written by the app when it
restarts, so a copy can also be kept in a GitHub repository (see GitHubStore).
"""

from __future__ import annotations

import base64
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from .http import DEFAULT_TIMEOUT, SourceError
from .models import ALL_SITES, Hotel, SiteRating

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "areas"

BASE_COLUMNS = [
    "name", "key", "hotel_class", "all_inclusive", "latitude", "longitude",
    "price_per_night", "currency", "address", "link", "amenities",
]
SITE_FIELDS = ["rating", "raw", "scale", "reviews", "url", "matched_name", "checked"]


def area_slug(area: str, all_inclusive: bool) -> str:
    text = unicodedata.normalize("NFKD", area)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "area"
    return f"{slug}__{'all-inclusive' if all_inclusive else 'all-hotels'}"


# ------------------------------------------------------------------ table <-> hotels
def hotels_to_df(hotels: list[Hotel]) -> pd.DataFrame:
    rows = []
    for h in hotels:
        row = {
            "name": h.name, "key": h.key, "hotel_class": h.hotel_class,
            "all_inclusive": h.is_all_inclusive, "latitude": h.latitude, "longitude": h.longitude,
            "price_per_night": h.price_per_night, "currency": h.currency, "address": h.address,
            "link": h.link, "amenities": "; ".join(h.amenities),
        }
        for site in ALL_SITES:
            r = h.ratings.get(site)
            row[f"{site}_rating"] = r.rating if r else None
            row[f"{site}_raw"] = r.raw_rating if r else None
            row[f"{site}_scale"] = r.scale if r else None
            row[f"{site}_reviews"] = r.reviews if r else None
            row[f"{site}_url"] = r.url if r else None
            row[f"{site}_matched_name"] = r.matched_name if r else None
            row[f"{site}_checked"] = h.checked.get(site)
        rows.append(row)
    columns = BASE_COLUMNS + [f"{s}_{f}" for s in ALL_SITES for f in SITE_FIELDS]
    return pd.DataFrame(rows, columns=columns)


def _value(row: dict, column: str):
    value = row.get(column)
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    return value


def df_to_hotels(df: pd.DataFrame) -> list[Hotel]:
    hotels = []
    for row in df.to_dict("records"):
        name = _value(row, "name")
        if not name:
            continue
        cls = _value(row, "hotel_class")
        amenities = _value(row, "amenities")
        hotel = Hotel(
            name=str(name),
            key=str(_value(row, "key") or name),
            hotel_class=int(float(cls)) if cls is not None else None,
            latitude=_float(_value(row, "latitude")),
            longitude=_float(_value(row, "longitude")),
            address=_value(row, "address"),
            link=_value(row, "link"),
            price_per_night=_float(_value(row, "price_per_night")),
            currency=_value(row, "currency"),
            amenities=[a.strip() for a in str(amenities).split(";") if a.strip()] if amenities else [],
        )
        if not hotel.amenities and _value(row, "all_inclusive") in (True, "True", "true", 1, "1"):
            hotel.amenities = ["All-inclusive available"]
        for site in ALL_SITES:
            checked = _value(row, f"{site}_checked")
            if checked:
                hotel.checked[site] = str(checked)[:10]
            raw = _float(_value(row, f"{site}_raw"))
            if raw is None:
                if checked:
                    hotel.ratings[site] = None  # checked, not found
                continue
            reviews = _value(row, f"{site}_reviews")
            hotel.ratings[site] = SiteRating.from_raw(
                site,
                raw,
                _float(_value(row, f"{site}_scale")) or 5.0,
                reviews=int(float(reviews)) if reviews is not None else None,
                url=_value(row, f"{site}_url"),
                matched_name=_value(row, f"{site}_matched_name"),
            )
        hotels.append(hotel)
    return hotels


def _float(value) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def read_table(data: bytes, filename: str) -> pd.DataFrame:
    """Read an uploaded CSV or Excel file."""
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    return pd.read_csv(io.BytesIO(data))


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, sheet_name="hotels")
    return buffer.getvalue()


# ------------------------------------------------------------------ storage backends
@dataclass
class AreaInfo:
    hotels: int
    sites_checked: list[str]  # sites that were checked for at least one hotel
    last_checked: Optional[str]


def summarize(hotels: list[Hotel]) -> AreaInfo:
    sites = [s for s in ALL_SITES if any(s in h.checked for h in hotels)]
    dates = [d for h in hotels for d in h.checked.values()]
    return AreaInfo(hotels=len(hotels), sites_checked=sites, last_checked=max(dates) if dates else None)


class LocalStore:
    def __init__(self, folder: Path = DEFAULT_DIR):
        self.folder = Path(folder)

    def path(self, slug: str) -> Path:
        return self.folder / f"{slug}.csv"

    def load(self, slug: str) -> Optional[list[Hotel]]:
        path = self.path(slug)
        if not path.exists():
            return None
        return df_to_hotels(pd.read_csv(path))

    def save(self, slug: str, hotels: list[Hotel]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        hotels_to_df(hotels).to_csv(self.path(slug), index=False)

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("*.csv")) if self.folder.exists() else []


class GitHubStore:
    """Keeps the area files in a GitHub repository branch, so they survive app restarts.

    Needs a fine-grained token with "Contents: read and write" on that repository only.
    The branch is created from the default branch the first time. Using a separate branch
    (default "resort-data") keeps data commits from restarting an app deployed from main.
    """

    API = "https://api.github.com"

    def __init__(self, token: str, repo: str, branch: str = "resort-data", folder: str = "data/areas",
                 session: Optional[requests.Session] = None):
        self.repo, self.branch, self.folder = repo, branch, folder.strip("/")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _url(self, path: str) -> str:
        return f"{self.API}/repos/{self.repo}/{path}"

    def _file(self, slug: str) -> str:
        return f"{self.folder}/{slug}.csv"

    def _get_file(self, slug: str) -> Optional[dict]:
        resp = self.session.get(self._url(f"contents/{self._file(slug)}"), params={"ref": self.branch},
                                timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 404:
            return None
        self._raise(resp)
        return resp.json()

    def load(self, slug: str) -> Optional[list[Hotel]]:
        meta = self._get_file(slug)
        if not meta:
            return None
        if meta.get("content"):
            data = base64.b64decode(meta["content"])
        else:  # files over 1 MB come without content
            resp = self.session.get(meta["download_url"], timeout=DEFAULT_TIMEOUT)
            self._raise(resp)
            data = resp.content
        return df_to_hotels(pd.read_csv(io.BytesIO(data)))

    def save(self, slug: str, hotels: list[Hotel]) -> None:
        self._ensure_branch()
        existing = self._get_file(slug)
        body = {
            "message": f"Update saved hotels for {slug}",
            "content": base64.b64encode(hotels_to_df(hotels).to_csv(index=False).encode()).decode(),
            "branch": self.branch,
        }
        if existing:
            body["sha"] = existing["sha"]
        resp = self.session.put(self._url(f"contents/{self._file(slug)}"), data=json.dumps(body),
                                timeout=DEFAULT_TIMEOUT)
        self._raise(resp)

    def list(self) -> list[str]:
        resp = self.session.get(self._url(f"contents/{self.folder}"), params={"ref": self.branch},
                                timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 404:
            return []
        self._raise(resp)
        return sorted(f["name"][:-4] for f in resp.json() if f["name"].endswith(".csv"))

    def _ensure_branch(self) -> None:
        resp = self.session.get(self._url(f"git/ref/heads/{self.branch}"), timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            return
        repo = self.session.get(self._url("").rstrip("/"), timeout=DEFAULT_TIMEOUT)
        self._raise(repo)
        default = repo.json()["default_branch"]
        head = self.session.get(self._url(f"git/ref/heads/{default}"), timeout=DEFAULT_TIMEOUT)
        self._raise(head)
        created = self.session.post(
            self._url("git/refs"),
            data=json.dumps({"ref": f"refs/heads/{self.branch}", "sha": head.json()["object"]["sha"]}),
            timeout=DEFAULT_TIMEOUT,
        )
        if created.status_code != 422:  # 422 = created meanwhile
            self._raise(created)

    @staticmethod
    def _raise(resp: requests.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise SourceError(f"GitHub storage: HTTP {resp.status_code} {detail}")


class AreaStore:
    """Local files first (fast), with an optional GitHub copy (permanent)."""

    def __init__(self, local: LocalStore, remote: Optional[GitHubStore] = None):
        self.local, self.remote = local, remote

    def load(self, slug: str) -> Optional[list[Hotel]]:
        hotels = self.local.load(slug)
        if hotels is None and self.remote:
            hotels = self.remote.load(slug)
            if hotels is not None:
                self.local.save(slug, hotels)
        return hotels

    def save(self, slug: str, hotels: list[Hotel]) -> Optional[str]:
        """Save locally and to GitHub. Returns a warning if the GitHub copy failed."""
        self.local.save(slug, hotels)
        if self.remote:
            try:
                self.remote.save(slug, hotels)
            except (SourceError, requests.RequestException) as exc:
                return f"Saved on the app server only; the GitHub copy failed: {exc}"
        return None

    def list(self) -> list[str]:
        names = set(self.local.list())
        if self.remote:
            try:
                names |= set(self.remote.list())
            except (SourceError, requests.RequestException):
                pass
        return sorted(names)
