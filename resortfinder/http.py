"""A shared HTTP session with retries, and a small thread-safe cache."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 30


class SourceError(RuntimeError):
    """A source failed (bad key, quota, network). Shown to the user in the UI."""


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
    session.headers["User-Agent"] = "ResortFinder/0.1"
    return session


def check_response(resp: requests.Response, source: str) -> Any:
    """Return the JSON body, or raise SourceError with a readable message."""
    try:
        data = resp.json()
    except ValueError:
        data = None
    if resp.status_code >= 400:
        detail = ""
        if isinstance(data, dict):
            detail = data.get("error") or data.get("message") or data.get("Message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message", str(detail))
        raise SourceError(f"{source}: HTTP {resp.status_code} {detail}".strip())
    if isinstance(data, dict) and data.get("error"):
        raise SourceError(f"{source}: {data['error']}")
    return data


class TTLCache:
    """In-memory cache so repeated searches don't spend API quota again."""

    def __init__(self, ttl_seconds: float = 7 * 24 * 3600):
        self.ttl = ttl_seconds
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: Any, compute: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = compute()
        with self._lock:
            self._data[key] = (now, value)
        return value

    def discard(self, key: Any) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
