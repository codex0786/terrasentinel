"""Temporal train/validation/test assignment with embargo gaps.

Rows inside an embargo gap are excluded from every split so that a fire event
spanning a boundary cannot place correlated rows on both sides.
Cutoff dates must be fixed in docs/research_protocol.md BEFORE looking at test results.
"""

from __future__ import annotations

import pandas as pd


def temporal_split(dates: pd.Series, train_end: str, val_end: str, embargo_days: int) -> pd.Series:
    if embargo_days < 0:
        raise ValueError("embargo_days must be non-negative")
    d = pd.to_datetime(dates, utc=True).dt.normalize()
    t_end = pd.Timestamp(train_end, tz="UTC")
    v_end = pd.Timestamp(val_end, tz="UTC")
    gap = pd.Timedelta(days=embargo_days)
    if v_end <= t_end + gap:
        raise ValueError("validation period is empty after applying the embargo")

    split = pd.Series("embargo", index=dates.index, dtype="object")
    split[d <= t_end] = "train"
    split[(d > t_end + gap) & (d <= v_end)] = "val"
    split[d > v_end + gap] = "test"
    return split


def geographic_holdout(regions: pd.Series, holdout: list[str]) -> pd.Series:
    """True for rows in held-out regions. Unknown region names are an error, not a silent no-op."""
    unknown = set(holdout) - set(regions.dropna().unique())
    if unknown:
        raise ValueError(f"holdout regions not present in data: {sorted(unknown)}")
    return regions.isin(holdout)
