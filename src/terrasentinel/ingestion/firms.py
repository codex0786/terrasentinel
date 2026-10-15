"""NASA FIRMS active-fire ingestion (area CSV API).

API format (checked against FIRMS docs on 2026-10-15):
    /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{YYYY-MM-DD}
DAY_RANGE is 1..5. DATE is the first day of the range.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from terrasentinel.ingestion.archive import ArchiveRecord, RawArchive
from terrasentinel.ingestion.http import FetchError, RateLimiter, fetch_with_retry

BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
MAX_DAY_RANGE = 5
SCIENCE_SOURCES = {"VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "MODIS_SP"}
NRT_SOURCES = {"VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"}
VALID_SOURCES = SCIENCE_SOURCES | NRT_SOURCES
EXPECTED_HEADER_PREFIX = b"latitude,longitude"
LIMIT_MESSAGE = "transaction limit"   # FIRMS answers HTTP 400 "Exceeding allowed transaction limit."
LIMIT_WINDOW_S = 610                  # FIRMS counts transactions over a rolling 10-minute window


class FirmsResponseError(FetchError):
    """FIRMS answered with HTTP 200 but the body is not a detection CSV (e.g. 'Invalid MAP_KEY')."""


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west < self.east <= 180 and -90 <= self.south < self.north <= 90):
            raise ValueError(f"Invalid bounding box: {self}")

    def as_param(self) -> str:
        return f"{self.west:g},{self.south:g},{self.east:g},{self.north:g}"


def iter_date_chunks(start: date, end: date, max_days: int = MAX_DAY_RANGE) -> Iterator[tuple[date, int]]:
    """Split the inclusive range [start, end] into (chunk_start, day_range) pieces."""
    if end < start:
        raise ValueError("end must be on or after start")
    if not 1 <= max_days <= MAX_DAY_RANGE:
        raise ValueError(f"max_days must be in 1..{MAX_DAY_RANGE}")
    cur = start
    while cur <= end:
        n = min(max_days, (end - cur).days + 1)
        yield cur, n
        cur += timedelta(days=n)


def area_url(map_key: str, source: str, bbox: BBox, day_range: int, start: date,
             base_url: str = BASE_URL) -> str:
    if source not in VALID_SOURCES:
        raise ValueError(f"Unknown FIRMS source {source!r}")
    if not 1 <= day_range <= MAX_DAY_RANGE:
        raise ValueError(f"day_range must be in 1..{MAX_DAY_RANGE}")
    return (f"{base_url}/api/area/csv/{map_key}/{source}/{bbox.as_param()}/"
            f"{day_range}/{start.isoformat()}")


def check_csv_body(content: bytes) -> None:
    head = content.lstrip()[:200]
    if not head.startswith(EXPECTED_HEADER_PREFIX):
        snippet = head.decode("utf-8", errors="replace").strip()
        raise FirmsResponseError(f"FIRMS returned a non-CSV body: {snippet!r}")


class FirmsClient:
    def __init__(self, map_key: str, archive: RawArchive, *,
                 session: requests.Session | None = None,
                 min_interval_s: float = 1.0, max_retries: int = 3, base_url: str = BASE_URL,
                 limit_retries: int = 6, limit_wait_s: float = LIMIT_WINDOW_S,
                 sleep: Callable[[float], None] = time.sleep):
        if not map_key:
            raise ValueError("FIRMS MAP_KEY is required")
        self.map_key = map_key
        self.archive = archive
        self.session = session or requests.Session()
        self.rate_limiter = RateLimiter(min_interval_s)
        self.max_retries = max_retries
        self.base_url = base_url
        self.limit_retries = limit_retries
        self.limit_wait_s = limit_wait_s
        self._sleep = sleep

    def _get(self, url: str) -> bytes:
        """Fetch, waiting out the MAP_KEY transaction window when FIRMS reports the limit is exhausted."""
        for attempt in range(self.limit_retries + 1):
            try:
                return fetch_with_retry(url, session=self.session, max_retries=self.max_retries,
                                        rate_limiter=self.rate_limiter, secrets=[self.map_key])
            except FetchError as exc:
                if LIMIT_MESSAGE not in str(exc).lower() or attempt == self.limit_retries:
                    raise
                print(f"  FIRMS transaction limit reached; waiting {self.limit_wait_s:.0f}s", flush=True)
                self._sleep(self.limit_wait_s)
        raise AssertionError("unreachable")

    def fetch_chunk(self, source: str, bbox: BBox, start: date, day_range: int) -> ArchiveRecord:
        url = area_url(self.map_key, source, bbox, day_range, start, self.base_url)
        content = self._get(url)
        check_csv_body(content)
        request = {  # never store the key
            "endpoint": "area/csv",
            "source": source,
            "bbox": bbox.as_param(),
            "start_date": start.isoformat(),
            "day_range": day_range,
        }
        return self.archive.store("firms", source, content, request)

    def archived_chunks(self, source: str, bbox: BBox) -> set[tuple[str, int]]:
        """(start_date, day_range) already archived for this source/bbox with an intact payload."""
        done = set()
        for r in self.archive.records():
            q = r.request
            if r.provider == "firms" and r.product == source and q.get("bbox") == bbox.as_param():
                if (self.archive.root / r.path).exists():
                    done.add((q["start_date"], int(q["day_range"])))
        return done

    def fetch_range(self, source: str, bbox: BBox, start: date, end: date,
                    max_requests: int = 200, skip_archived: bool = False) -> list[ArchiveRecord]:
        chunks = list(iter_date_chunks(start, end))
        if skip_archived:
            done = self.archived_chunks(source, bbox)
            chunks = [(s, n) for s, n in chunks if (s.isoformat(), n) not in done]
        if len(chunks) > max_requests:
            raise ValueError(f"{len(chunks)} requests exceeds the max_requests budget of {max_requests}")
        return [self.fetch_chunk(source, bbox, s, n) for s, n in chunks]
