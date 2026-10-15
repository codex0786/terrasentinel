"""Trailing meteorological features from NASA POWER (MERRA-2) for cell-date rows.

Rule (same as the fire features): a row for day D sees weather for days <= D-1 only.
POWER daily values are requested in UTC, so day D-1 is complete at the D 00:00 UTC cutoff.
Science-mode experiments assume POWER is available immediately (documented simplification).

Anomalies are departures from a per-grid-point day-of-year climatology computed only from
`climatology_years`, which must end before the first label day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

POWER_LAT_STEP = 0.5
POWER_LON_STEP = 0.625
WEATHER_VARS = ("T2M_MAX", "RH2M", "WS2M", "PRECTOTCORR")
RAIN_DAY_MM = 1.0
DRY_DAYS_CAP = 60


def nearest_power_point(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    lat = np.round(np.asarray(lat, float) / POWER_LAT_STEP) * POWER_LAT_STEP
    lon = np.round(np.asarray(lon, float) / POWER_LON_STEP) * POWER_LON_STEP
    return np.round(lat, 4), np.round(lon, 4)


def climatology(weather: pd.DataFrame, years: tuple[int, int], half_window_days: int = 15) -> pd.DataFrame:
    """Mean of each variable per (lat, lon, day-of-year) over `years`, smoothed with a circular
    +/- half_window_days moving average. Day 366 is folded into 365."""
    y = weather["date"].dt.year
    w = weather[(y >= years[0]) & (y <= years[1])]
    if w.empty:
        raise ValueError(f"no weather data in climatology years {years}")
    doy = np.minimum(w["date"].dt.dayofyear, 365)
    m = w.assign(doy=doy).groupby(["lat", "lon", "doy"])[list(WEATHER_VARS)].mean()
    full = pd.MultiIndex.from_product([m.index.levels[0], m.index.levels[1], range(1, 366)],
                                      names=["lat", "lon", "doy"])
    m = m.reindex(full)
    k = 2 * half_window_days + 1
    out = []
    for (la, lo), g in m.groupby(level=["lat", "lon"], sort=False):
        if g.isna().all().all():
            continue
        vals = g.to_numpy()
        padded = np.vstack([vals[-half_window_days:], vals, vals[:half_window_days]])
        sm = pd.DataFrame(padded).rolling(k, center=True, min_periods=1).mean().to_numpy()
        sm = sm[half_window_days:-half_window_days]
        out.append(pd.DataFrame(sm, columns=list(WEATHER_VARS)).assign(lat=la, lon=lo, doy=range(1, 366)))
    return pd.concat(out, ignore_index=True)


def _days_since_rain(precip: np.ndarray) -> np.ndarray:
    """For each day t: days since the last rain day strictly before t (cap DRY_DAYS_CAP)."""
    out = np.empty(len(precip))
    since = DRY_DAYS_CAP
    for i, p in enumerate(precip):
        out[i] = since                      # uses days < i only
        since = 1 if (not np.isnan(p) and p >= RAIN_DAY_MM) else min(since + 1, DRY_DAYS_CAP)
    return out


def point_features(series: pd.DataFrame, clim: pd.DataFrame | None) -> pd.DataFrame:
    """series: one grid point, columns date + WEATHER_VARS, any order/gaps. Returns one row per
    calendar day with features computed from days strictly before that day."""
    s = series.set_index("date").sort_index()
    idx = pd.date_range(s.index.min(), s.index.max() + pd.Timedelta(days=1), freq="D", tz="UTC")
    s = s.reindex(idx)[list(WEATHER_VARS)]
    if clim is not None:
        c = clim.set_index("doy")
        doy = np.minimum(s.index.dayofyear, 365)
        anom = s.to_numpy() - c.loc[doy, list(WEATHER_VARS)].to_numpy()
        a = pd.DataFrame(anom, index=s.index, columns=list(WEATHER_VARS))
    lag = s.shift(1)                         # value for day t-1 sits on row t
    f = pd.DataFrame(index=s.index)
    f["t2m_max_3d"] = lag["T2M_MAX"].rolling(3, min_periods=2).mean()
    f["rh2m_3d"] = lag["RH2M"].rolling(3, min_periods=2).mean()
    f["ws2m_3d"] = lag["WS2M"].rolling(3, min_periods=2).mean()
    f["precip_7d"] = lag["PRECTOTCORR"].rolling(7, min_periods=5).sum()
    f["dry_days"] = _days_since_rain(s["PRECTOTCORR"].to_numpy())
    if clim is not None:
        alag = a.shift(1)
        f["t2m_max_anom_3d"] = alag["T2M_MAX"].rolling(3, min_periods=2).mean()
        f["rh2m_anom_3d"] = alag["RH2M"].rolling(3, min_periods=2).mean()
        f["precip_anom_30d"] = alag["PRECTOTCORR"].rolling(30, min_periods=21).sum()
    return f.rename_axis("date").reset_index()


def build_weather_features(weather: pd.DataFrame, rows: pd.DataFrame, cell_lat, cell_lon,
                           climatology_years: tuple[int, int], first_label_day: str) -> pd.DataFrame:
    """Attach weather features to rows (cell_id, date). cell_lat/cell_lon: cell centres aligned with rows."""
    if pd.Timestamp(f"{climatology_years[1]}-12-31", tz="UTC") >= pd.Timestamp(first_label_day, tz="UTC"):
        raise ValueError("climatology years must end before the first label day")
    plat, plon = nearest_power_point(cell_lat, cell_lon)
    keys = rows[["cell_id", "date"]].assign(lat=plat, lon=plon)
    need = keys[["lat", "lon"]].drop_duplicates()
    w = weather.merge(need, on=["lat", "lon"], how="inner")
    clim = climatology(w, climatology_years)
    feats = []
    clim_groups = dict(tuple(clim.groupby(["lat", "lon"])))
    for (la, lo), g in w.groupby(["lat", "lon"], sort=False):
        f = point_features(g, clim_groups.get((la, lo)))
        feats.append(f.assign(lat=la, lon=lo))
    feats = pd.concat(feats, ignore_index=True)
    out = keys.merge(feats, on=["lat", "lon", "date"], how="left").drop(columns=["lat", "lon"])
    return rows.merge(out, on=["cell_id", "date"], how="left")
