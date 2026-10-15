"""Workstream B v0 (docs/protocol_rainfall_v0.md): state x day rainfall features and event labels.

Arrays are (day, cell) over the cells assigned to a state. All thresholds come from the climatology
years only, which end before every label year.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

RAIN_CAUSE = re.compile(r"rain|flood|cloudburst", re.I)
MAX_EVENT_DAYS = 30
MIN_STATE_CELLS = 10


def three_day_totals(daily: np.ndarray, prev2: np.ndarray | None = None) -> np.ndarray:
    """Sum over D-2..D for each day. prev2: the two days before daily[0] (NaN if unavailable)."""
    if prev2 is None:
        prev2 = np.full((2, daily.shape[1]), np.nan, dtype=daily.dtype)
    x = np.concatenate([prev2, daily], axis=0)
    return x[2:] + x[1:-1] + x[:-2]


def monthly_thresholds(values: np.ndarray, months: np.ndarray, q: float = 99.0) -> np.ndarray:
    """(12, cell) q-th percentile per cell for each calendar month m, pooling months m-1, m, m+1."""
    out = np.full((12, values.shape[1]), np.nan, dtype=np.float32)
    for m in range(1, 13):
        pool = {(m - 2) % 12 + 1, m, m % 12 + 1}
        sel = np.isin(months, list(pool))
        if sel.any():
            out[m - 1] = np.nanpercentile(values[sel], q, axis=0)
    return out


def state_features(daily: np.ndarray, three: np.ndarray, months: np.ndarray, thr1: np.ndarray,
                   thr3: np.ndarray, cell_state: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """One row per (state, day): mean_1d, mean_3d, frac_p99_1d, frac_p99_3d, max_3d."""
    exc1 = daily > thr1[months - 1]
    exc3 = three > thr3[months - 1]
    frames = []
    for s in pd.unique(cell_state):
        c = cell_state == s
        frames.append(pd.DataFrame({
            "state": s, "date": dates,
            "mean_1d": np.nanmean(daily[:, c], axis=1), "mean_3d": np.nanmean(three[:, c], axis=1),
            "frac_p99_1d": exc1[:, c].mean(axis=1), "frac_p99_3d": exc3[:, c].mean(axis=1),
            "max_3d": np.nanmax(three[:, c], axis=1),
        }))
    return pd.concat(frames, ignore_index=True)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())


def event_state_days(events: pd.DataFrame, state_names: list[str], aliases: dict[str, str],
                     start: str, end: str) -> tuple[pd.DataFrame, dict]:
    """IFI events -> (state, date) positives within [start, end] plus a report of what was dropped."""
    lookup = {_norm(n): n for n in state_names}
    ev = events.copy()
    ev["start"] = pd.to_datetime(ev["Start Date"], format="%d-%m-%Y %H:%M", errors="coerce", utc=True).dt.normalize()
    ev["end"] = pd.to_datetime(ev["End Date"], format="%d-%m-%Y %H:%M", errors="coerce", utc=True).dt.normalize()
    rep = {"events_in": len(ev), "unparseable_dates": int((ev["start"].isna() | ev["end"].isna()).sum())}
    ev = ev.dropna(subset=["start", "end"])
    ev = ev[ev["end"] >= ev["start"]]
    ev = ev[ev["Main Cause"].fillna("").str.contains(RAIN_CAUSE)]
    rep["rain_related"] = len(ev)
    long = (ev["end"] - ev["start"]).dt.days + 1 > MAX_EVENT_DAYS
    rep["dropped_longer_than_30d"] = int(long.sum())
    ev = ev[~long]
    lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    ev = ev[(ev["end"] >= lo) & (ev["start"] <= hi)]
    rows, unmatched = [], set()
    for _, e in ev.iterrows():
        for tok in str(e["State"]).split(","):
            tok = tok.strip()
            if not tok:
                continue
            name = aliases.get(tok) or lookup.get(_norm(tok))
            if name is None:
                unmatched.add(tok)
                continue
            for d in pd.date_range(max(e["start"], lo), min(e["end"], hi), freq="D"):
                rows.append((name, d))
    rep["events_in_window"] = len(ev)
    rep["unmatched_state_tokens"] = sorted(unmatched)
    pos = pd.DataFrame(rows, columns=["state", "date"]).drop_duplicates()
    return pos, rep
