"""NASA POWER daily regional ingestion (MERRA-2 meteorology).

API limits (checked 2026-10-15): one parameter per request, <= 10 degrees per side,
<= 366 days per request. Daily values default to LST; we always request UTC so weather days
line up with the UTC label days.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

import requests

from terrasentinel.ingestion.archive import ArchiveRecord, RawArchive
from terrasentinel.ingestion.http import FetchError, RateLimiter, fetch_with_retry

REGIONAL_URL = "https://power.larc.nasa.gov/api/temporal/daily/regional"
MAX_SPAN_DEG = 10.0
HEADER_END = b"-END HEADER-"


class PowerResponseError(FetchError):
    """POWER returned HTTP 200 with a body that is not a regional CSV."""


@dataclass(frozen=True)
class Tile:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def __post_init__(self) -> None:
        if not (0 < self.lat_max - self.lat_min <= MAX_SPAN_DEG and 0 < self.lon_max - self.lon_min <= MAX_SPAN_DEG):
            raise ValueError(f"tile exceeds POWER regional limits: {self}")

    def key(self) -> str:
        return f"{self.lat_min:g},{self.lat_max:g},{self.lon_min:g},{self.lon_max:g}"


def tiles_for(bbox: dict, lat_step: float = 8.0, lon_step: float = 10.0, skip=()) -> list[Tile]:
    """Cover bbox with tiles no larger than POWER allows. `skip`: tile keys known to contain no study area."""
    tiles = []
    lat = bbox["south"]
    while lat < bbox["north"]:
        lon = bbox["west"]
        while lon < bbox["east"]:
            t = Tile(lat, min(lat + lat_step, bbox["north"]), lon, min(lon + lon_step, bbox["east"]))
            if t.key() not in skip:
                tiles.append(t)
            lon += lon_step
        lat += lat_step
    return tiles


def year_ranges(first_year: int, last_year: int) -> Iterator[tuple[date, date]]:
    for y in range(first_year, last_year + 1):
        yield date(y, 1, 1), date(y, 12, 31)


def check_regional_csv(content: bytes) -> None:
    if HEADER_END not in content[:5000]:
        raise PowerResponseError(f"POWER returned a non-CSV body: {content[:200]!r}")


class PowerClient:
    def __init__(self, archive: RawArchive, *, session: requests.Session | None = None,
                 community: str = "AG", min_interval_s: float = 1.0, max_retries: int = 3):
        self.archive = archive
        self.session = session or requests.Session()
        self.community = community
        self.rate_limiter = RateLimiter(min_interval_s)
        self.max_retries = max_retries

    def url(self, parameter: str, tile: Tile, start: date, end: date) -> str:
        if (end - start).days >= 366:
            raise ValueError("POWER allows at most 366 days per request")
        q = urlencode({
            "latitude-min": tile.lat_min, "latitude-max": tile.lat_max,
            "longitude-min": tile.lon_min, "longitude-max": tile.lon_max,
            "parameters": parameter, "community": self.community,
            "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
            "format": "CSV", "time-standard": "UTC",
        })
        return f"{REGIONAL_URL}?{q}"

    def fetch(self, parameter: str, tile: Tile, start: date, end: date) -> ArchiveRecord:
        content = fetch_with_retry(self.url(parameter, tile, start, end), session=self.session,
                                   max_retries=self.max_retries, rate_limiter=self.rate_limiter, timeout_s=300)
        check_regional_csv(content)
        request = {"endpoint": "daily/regional", "parameter": parameter, "tile": tile.key(),
                   "start_date": start.isoformat(), "end_date": end.isoformat(),
                   "community": self.community, "time_standard": "UTC"}
        return self.archive.store("nasa_power", parameter, content, request)

    def archived(self) -> set[tuple[str, str, str]]:
        return {(r.product, r.request["tile"], r.request["start_date"]) for r in self.archive.records()
                if r.provider == "nasa_power" and (self.archive.root / r.path).exists()}
