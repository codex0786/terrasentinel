"""Build the Workstream B v0 state x day dataset (docs/protocol_rainfall_v0.md).

Needs data/interim/imerg/imerg_india_<year>.nc for 2001-2023 (pipelines/build_imerg.py).
Writes data/processed/rainfall_v0/rows.parquet and manifest.json.
"""

from __future__ import annotations

import hashlib
import io
import json

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.geospatial.boundary import cell_regions, load_boundary
from terrasentinel.geospatial.grid import Grid
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.rainfall.core import (
    MIN_STATE_CELLS,
    event_state_days,
    monthly_thresholds,
    state_features,
    three_day_totals,
)

CLIM = (2001, 2014)
LABEL = (2015, 2023)


def load_years(years, lat_idx, lon_idx):
    """(dates, daily[day, cell]) for the chosen cells across years."""
    dates, arrays = [], []
    for y in years:
        ds = xr.open_dataset(data_dir() / "interim" / "imerg" / f"imerg_india_{y}.nc", engine="h5netcdf")
        full = pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="D")
        pr = ds["precipitation"].reindex(time=full).values           # missing days -> NaN
        arrays.append(pr[:, lat_idx, lon_idx].astype(np.float32))
        dates.append(full)
    return pd.DatetimeIndex(np.concatenate(dates)).tz_localize("UTC"), np.concatenate(arrays)


def main() -> None:
    india = load_yaml("india.yaml")
    region = india["region"]
    grid = Grid.from_config(india)
    boundary = load_boundary(data_dir() / region["boundary_file"], region["boundary_name_field"])
    ds0 = xr.open_dataset(data_dir() / "interim" / "imerg" / f"imerg_india_{LABEL[1]}.nc", engine="h5netcdf")
    lats, lons = ds0["lat"].values, ds0["lon"].values
    lat2, lon2 = np.meshgrid(lats, lons, indexing="ij")
    cid = pd.Series(grid.cell_id(lat2.ravel(), lon2.ravel()))
    st = cell_regions(grid, cid, boundary).set_index("cell_id")["cell_region"].reindex(cid).to_numpy()
    inside = pd.notna(st)
    counts = pd.Series(st[inside]).value_counts()
    keep_states = set(counts[counts >= MIN_STATE_CELLS].index)
    sel = inside & pd.Series(st).isin(keep_states).to_numpy()
    lat_idx, lon_idx = np.unravel_index(np.nonzero(sel)[0], lat2.shape)
    cell_state = st[sel]
    print(f"{sel.sum():,} cells in {len(keep_states)} states; excluded (<{MIN_STATE_CELLS} cells): "
          f"{sorted(set(counts.index) - keep_states)}", flush=True)

    cd, clim = load_years(range(CLIM[0], CLIM[1] + 1), lat_idx, lon_idx)
    clim3 = three_day_totals(clim)
    months = cd.month.to_numpy()
    thr1, thr3 = monthly_thresholds(clim, months), monthly_thresholds(clim3, months)
    prev2 = clim[-2:]
    del clim, clim3
    print("climatology thresholds done", flush=True)

    ld, daily = load_years(range(LABEL[0], LABEL[1] + 1), lat_idx, lon_idx)
    three = three_day_totals(daily, prev2=prev2)
    feats = state_features(daily, three, ld.month.to_numpy(), thr1, thr3, cell_state, ld)
    missing_days = ld[np.isnan(daily).all(axis=1)]
    feats = feats[~feats["date"].isin(missing_days)]

    archive = RawArchive(data_dir() / "raw")
    ifi = next(r for r in archive.records() if r.request.get("file") == "India_Flood_Inventory_v3.csv")
    events = pd.read_csv(io.BytesIO(archive.read(ifi)), encoding_errors="replace")
    aliases = yaml.safe_load((REPO_ROOT / "configs" / "rainfall_state_aliases.yaml").read_text())["aliases"]
    pos, rep = event_state_days(events, sorted(boundary["region"].unique()), aliases,
                                f"{LABEL[0]}-01-01", f"{LABEL[1]}-12-31")
    rows = feats.merge(pos.assign(label=1), on=["state", "date"], how="left")
    rows["label"] = rows["label"].fillna(0).astype(int)
    out = data_dir() / "processed" / "rainfall_v0"
    out.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out / "rows.parquet", index=False)
    manifest = {
        "cells": int(sel.sum()), "states": sorted(keep_states), "climatology_years": CLIM, "label_years": LABEL,
        "imerg_missing_days_excluded": [d.date().isoformat() for d in missing_days],
        "label_report": rep, "rows": len(rows), "positives": int(rows["label"].sum()),
        "positive_state_days_outside_kept_states": int((~pos["state"].isin(keep_states)).sum()),
        "ifi_sha256": ifi.sha256,
        "protocol_sha256": hashlib.sha256((REPO_ROOT / "docs" / "protocol_rainfall_v0.md").read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({k: v for k, v in manifest.items() if k != "states"}, indent=2, default=str))


if __name__ == "__main__":
    main()
