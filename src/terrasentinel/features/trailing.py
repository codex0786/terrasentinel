"""Trailing-window fire features for cell-date rows.

A row (cell_id, date D) is scored at cutoff = D 00:00 UTC. A detection may contribute
only if it was *available* strictly before the cutoff (available_at_utc < cutoff).
Because availability >= acquisition time, this also excludes anything acquired on or
after D. Windows are [cutoff - w days, cutoff) on acquisition time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAY_NS = np.int64(86_400 * 10**9)


def attach_availability(det: pd.DataFrame, lag_hours: float) -> pd.DataFrame:
    """Add available_at_utc = acquisition time + the source's publication lag."""
    if lag_hours < 0:
        raise ValueError("lag_hours must be non-negative")
    return det.assign(
        available_at_utc=det["acq_datetime_utc"] + pd.Timedelta(hours=lag_hours)
    )


def _to_ns(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).astype("datetime64[ns, UTC]").to_numpy("datetime64[ns]").astype(np.int64)


def cutoff_for(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates, utc=True).dt.normalize()


def build_trailing_features(
    det: pd.DataFrame,
    rows: pd.DataFrame,
    windows_days: list[int],
    days_since_cap: float = 365.0,
) -> pd.DataFrame:
    """Return `rows` with fire_count_{w}d and days_since_last_fire columns added.

    det:  cell_id, acq_datetime_utc, available_at_utc
    rows: cell_id, date
    """
    for col in ("cell_id", "acq_datetime_utc", "available_at_utc"):
        if col not in det.columns:
            raise KeyError(f"detections missing column {col!r}")

    out = rows.reset_index(drop=True).copy()
    cut = _to_ns(cutoff_for(out["date"]))
    has_frp = "frp" in det.columns
    feats = {f"fire_count_{w}d": np.zeros(len(out), dtype=np.int64) for w in windows_days}
    if has_frp:  # missing FRP values contribute 0 to sums
        feats |= {f"frp_sum_{w}d": np.zeros(len(out)) for w in windows_days}
    since = np.full(len(out), float(days_since_cap))

    det_groups = {
        cid: (_to_ns(g["acq_datetime_utc"]), _to_ns(g["available_at_utc"]),
              np.nan_to_num(g["frp"].to_numpy(float)) if has_frp else None)
        for cid, g in det.groupby("cell_id", sort=False)
    }
    for cid, idx in out.groupby("cell_id", sort=False).indices.items():
        if cid not in det_groups:
            continue
        acq, avail, frp = det_groups[cid]
        c = cut[idx][:, None]
        visible = avail[None, :] < c
        for w in windows_days:
            in_win = visible & (acq[None, :] >= c - w * DAY_NS)
            feats[f"fire_count_{w}d"][idx] = in_win.sum(axis=1)
            if has_frp:
                feats[f"frp_sum_{w}d"][idx] = (in_win * frp[None, :]).sum(axis=1)
        last = np.where(visible, acq[None, :], np.iinfo(np.int64).min).max(axis=1)
        has = last > np.iinfo(np.int64).min
        days = (c[:, 0] - last) / DAY_NS
        since[idx] = np.where(has, np.minimum(days, days_since_cap), days_since_cap)

    for name, values in feats.items():
        out[name] = values
    out["days_since_last_fire"] = since
    return out
