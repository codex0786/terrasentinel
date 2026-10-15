"""Fire-persistence labels (Workstream A, primary outcome).

Population for day D: cells with >= 1 qualifying detection acquired on UTC day D-1
that was available before the D cutoff (so eligibility is knowable at prediction time).
Label: 1 if >= 1 qualifying detection is acquired in the cell on UTC day D, else 0.

A label of 0 means "no detection", not "confirmed no fire" (clouds, overpass gaps,
detection limits). See docs/limitations.md.

Days on which the source made no observation at all (sensor outages) are excluded as label
days: an outage would otherwise turn every eligible cell into a false "fire stopped" label.
"""

from __future__ import annotations

import pandas as pd

from terrasentinel.features.trailing import cutoff_for


def filter_qualifying(det: pd.DataFrame, allowed_classes=("nominal", "high")) -> pd.DataFrame:
    return det[det["confidence_class"].isin(allowed_classes)]


def find_unobserved_days(det: pd.DataFrame, start: str, end: str, known_outages=()) -> pd.DatetimeIndex:
    """Days in [start, end] with zero detections across the whole study area, plus documented outages.

    Zero detections over all of India in a day is treated as "no observation", not "no fire".
    known_outages: iterable of (first_day, last_day) inclusive.
    """
    days = pd.date_range(start, end, freq="D", tz="UTC")
    seen = set(cutoff_for(det["acq_datetime_utc"]).unique())
    missing = {d for d in days if d not in seen}
    for first, last in known_outages:
        missing |= set(pd.date_range(first, last, freq="D", tz="UTC")) & set(days)
    return pd.DatetimeIndex(sorted(missing))


def build_persistence_rows(det: pd.DataFrame, start: str, end: str, unobserved_days=()) -> pd.DataFrame:
    """det must already be filtered to qualifying detections and carry available_at_utc."""
    d = det.assign(acq_day=cutoff_for(det["acq_datetime_utc"]))
    days = pd.date_range(start, end, freq="D", tz="UTC")
    days = days[~days.isin(pd.DatetimeIndex(unobserved_days))]

    prev = d.assign(date=d["acq_day"] + pd.Timedelta(days=1))
    prev = prev[prev["available_at_utc"] < prev["date"]]
    population = (prev[prev["date"].isin(days)][["cell_id", "date"]]
                  .drop_duplicates().reset_index(drop=True))

    positives = d[["cell_id", "acq_day"]].drop_duplicates().rename(columns={"acq_day": "date"})
    positives["label"] = 1
    rows = population.merge(positives, on=["cell_id", "date"], how="left")
    rows["label"] = rows["label"].fillna(0).astype(int)
    return rows.sort_values(["date", "cell_id"]).reset_index(drop=True)
