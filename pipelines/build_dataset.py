"""Build the fire-persistence dataset from the normalized FIRMS snapshot (output of audit.py).

    python pipelines/build_dataset.py --experiment configs/experiments/fire_persistence_v0.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from terrasentinel.config import data_dir, load_yaml
from terrasentinel.experiments.fire_persistence import build_dataset, prepare_detections
from terrasentinel.geospatial.boundary import load_boundary
from terrasentinel.geospatial.grid import Grid
from terrasentinel.labels.persistence import find_unobserved_days


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment", required=True, type=Path)
    p.add_argument("--allow-bbox", action="store_true",
                   help="proceed without an India boundary (exploratory only; output is marked bbox_only)")
    args = p.parse_args()

    exp = yaml.safe_load(args.experiment.read_text())
    ds = exp["dataset"]
    for key in ("start", "end", "history_start"):
        if not ds.get(key):
            raise SystemExit(f"dataset.{key} is not set in {args.experiment}. Fix it from the data audit first.")
    india = load_yaml("india.yaml")
    feats = load_yaml("features.yaml")
    region = india["region"]

    boundary = None
    if region.get("boundary_file"):
        boundary = load_boundary(data_dir() / region["boundary_file"], region["boundary_name_field"])
    elif not args.allow_bbox:
        raise SystemExit("No boundary_file in configs/india.yaml. Run pipelines/fetch_boundary.py, "
                         "or pass --allow-bbox for exploratory output.")

    snapshots = {src: data_dir() / "interim" / f"firms_normalized_{src}.parquet" for src in ds["sources"]}
    missing = [str(p) for p in snapshots.values() if not p.exists()]
    if missing:
        raise SystemExit(f"Missing normalized snapshots {missing}. Run pipelines/audit.py first.")
    grid = Grid.from_config(india)
    lag = feats["prediction"]["availability_lag_hours"]["science"]
    known = load_yaml("data_sources.yaml")["firms"].get("known_outages", {})

    parts, info, unobserved = [], {}, pd.DatetimeIndex([], tz="UTC")
    for src, path in snapshots.items():
        d, i = prepare_detections(pd.read_parquet(path), grid, boundary, region["bbox"], lag)
        info[src] = i
        # A label day is unobserved if ANY contributing sensor was out: mixing a one-sensor day with
        # two-sensor days would change what a label of 0 means.
        gaps = find_unobserved_days(d, ds["start"], ds["end"], [tuple(o) for o in known.get(src, [])])
        info[src]["unobserved_days"] = [x.date().isoformat() for x in gaps]
        unobserved = unobserved.union(gaps)
        parts.append(d)
        print(f"{src}: {i}  unobserved label days: {len(gaps)}")
    det = pd.concat(parts, ignore_index=True)
    del parts
    if len(unobserved):
        print(f"Excluding {len(unobserved)} unobserved label day(s) (union over sources)")
    rows = build_dataset(det, grid, boundary, ds["start"], ds["end"],
                         feats["features"]["trailing_count_windows_days"], feats["features"]["days_since_last_cap"],
                         unobserved)

    out_dir = data_dir() / "processed" / exp["experiment"]
    out_dir.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out_dir / "rows.parquet", index=False)
    det.to_parquet(out_dir / "detections.parquet", index=False)
    config_hash = hashlib.sha256(json.dumps([exp, india, feats], sort_keys=True, default=str).encode()).hexdigest()
    manifest = {
        "per_source": info,
        "experiment": exp["experiment"],
        "config_sha256": config_hash,
        "snapshot_sha256": {src: hashlib.sha256(p.read_bytes()).hexdigest() for src, p in snapshots.items()},
        "unobserved_label_days_excluded": [d.date().isoformat() for d in unobserved],
        "rows": len(rows),
        "positives": int(rows["label"].sum()),
        "prevalence": float(rows["label"].mean()) if len(rows) else None,
        "cells": int(rows["cell_id"].nunique()),
        "regions": rows["cell_region"].value_counts(dropna=False).to_dict(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("regions", "per_source")}, indent=2, default=str))


if __name__ == "__main__":
    main()
