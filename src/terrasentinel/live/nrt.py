"""Near-real-time (NRT) operation.

NRT files for a given day keep filling in as granules arrive, so the same 1-day request can return
more rows later. Every retrieval is archived; for analysis the *latest* retrieval of each
(source, day) is used. Earlier versions stay in the archive, so revisions can be measured.

The locked research model is applied unchanged. The prediction-time rule is the same as in the
study (available_at < D 00:00 UTC), with the configured NRT publication lag. A label for day D is
final only once D has ended and the lag has passed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from terrasentinel.ingestion.archive import ArchiveRecord, RawArchive
from terrasentinel.ingestion.firms import BBox, FirmsClient
from terrasentinel.validation.firms_schema import normalize_firms, read_firms_csv

NRT_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT")
SP_EQUIVALENT = {"VIIRS_SNPP_NRT": "VIIRS_SNPP_SP", "VIIRS_NOAA20_NRT": "VIIRS_NOAA20_SP"}


def latest_by_day(archive: RawArchive, sources=NRT_SOURCES, bbox: BBox | None = None) -> dict[tuple[str, str],
                                                                                                ArchiveRecord]:
    """Most recent 1-day retrieval per (source, day)."""
    out: dict[tuple[str, str], ArchiveRecord] = {}
    for r in archive.records():
        q = r.request
        if r.provider != "firms" or r.product not in sources or int(q.get("day_range", 0)) != 1:
            continue
        if bbox is not None and q.get("bbox") != bbox.as_param():
            continue
        key = (r.product, q["start_date"])
        if key not in out or r.retrieved_at_utc > out[key].retrieved_at_utc:
            out[key] = r
    return out


def plan_fetch(have: dict, sources, first: date, last: date, refresh_days: int, today: date) -> list[tuple[str, date]]:
    """Days to (re)fetch: any day not yet archived, plus every day within `refresh_days` of today."""
    plan = []
    d = first
    while d <= last:
        for s in sources:
            if (s, d.isoformat()) not in have or (today - d).days < refresh_days:
                plan.append((s, d))
        d += timedelta(days=1)
    return plan


def fetch_nrt(client: FirmsClient, bbox: BBox, first: date, last: date, refresh_days: int = 3,
              today: date | None = None, sources=NRT_SOURCES) -> list[ArchiveRecord]:
    today = today or datetime.now(UTC).date()
    have = latest_by_day(client.archive, sources, bbox)
    return [client.fetch_chunk(s, bbox, d, 1) for s, d in plan_fetch(have, sources, first, last, refresh_days, today)]


def load_nrt(archive: RawArchive, first: date, last: date, sources=NRT_SOURCES,
             bbox: BBox | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalized detections from the latest retrieval of each (source, day) in [first, last], plus a
    per-(source, day) inventory: retrieval time, rows, and whether the day had zero detections."""
    frames, inv = [], []
    for (src, day), r in sorted(latest_by_day(archive, sources, bbox).items()):
        d = date.fromisoformat(day)
        if not first <= d <= last:
            continue
        df, rep = normalize_firms(read_firms_csv(archive.read(r)), src)
        df = df[df["acq_datetime_utc"].dt.date == d]   # a 1-day request should only return that day
        frames.append(df)
        inv.append({"source": src, "day": d, "retrieved_at_utc": r.retrieved_at_utc, "rows": len(df),
                    "sha256": r.sha256})
    det = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return det, pd.DataFrame(inv)


def label_final(day: date, now: datetime, lag_hours: float) -> bool:
    """Day D's outcome is final once D has ended and the publication lag (plus a margin) has passed."""
    end = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)
    return now >= end + timedelta(hours=2 * lag_hours)
