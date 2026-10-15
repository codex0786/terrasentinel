"""Fit the locked models on the training set exactly as specified and save predictions for every
cell-day, for the dashboard. Writes:
    data/processed/<experiment>/scores.parquet
    data/processed/<experiment>/scores_meta.json

No model selection or refitting on validation/test happens here; the fitted models are the
same specification as the locked evaluation (deterministic: identical inputs give identical scores).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.experiments.fire_persistence import assign_sets
from terrasentinel.geospatial.grid import Grid
from terrasentinel.models.baselines import LogisticModel, SeasonalBaseline


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment", required=True, type=Path)
    args = p.parse_args()
    cfg = yaml.safe_load(args.experiment.read_text())
    d = data_dir() / "processed" / cfg["experiment"]
    rows = pd.read_parquet(d / "rows.parquet")
    det = pd.read_parquet(d / "detections.parquet", columns=["cell_id", "acq_datetime_utc", "source"])
    rows["set"] = assign_sets(rows, cfg["split"])
    train = rows[rows["set"] == "train"]

    m = cfg["models"]
    seasonal = dict(m["seasonal"])
    hist_src = seasonal.pop("history_sources", None)
    hist = det if not hist_src else det[det["source"].isin(hist_src)]
    models = {
        "B0": SeasonalBaseline(hist, cfg["dataset"]["history_start"], **seasonal),
        "B1": LogisticModel(m["satellite_only_features"]),
        "M2": LogisticModel(m["satellite_only_features"] + m["meteorology_features"], name="M2_meteorology",
                            log_features=m["satellite_only_features"] + m.get("meteorology_log_features", [])),
    }
    out = rows[["cell_id", "date", "set", "cell_region", "label", "fire_count_1d", "frp_sum_1d"]].copy()
    for name, model in models.items():
        model.fit(train)
        out[f"p_{name}"] = model.predict(rows).astype("float32")
        print(f"{name}: fitted on {len(train):,} training rows; scored {len(rows):,}", flush=True)

    grid = Grid.from_config(load_yaml("india.yaml"))
    rc = out["cell_id"].str.extract(r"^r(-?\d+)_c(-?\d+)$").astype(int)
    out["lat"] = (grid.origin_lat + (rc[0] + 0.5) * grid.resolution_deg).astype("float32")
    out["lon"] = (grid.origin_lon + (rc[1] + 0.5) * grid.resolution_deg).astype("float32")
    out.to_parquet(d / "scores.parquet", index=False)

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                            capture_output=True, text=True).stdout.strip() or None
    meta = {
        "experiment": cfg["experiment"],
        "scored_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_commit": commit,
        "config_sha256": hashlib.sha256(args.experiment.read_bytes()).hexdigest(),
        "rows_sha256": hashlib.sha256((d / "rows.parquet").read_bytes()).hexdigest(),
        "trained_on": f"{train['date'].min().date()}..{train['date'].max().date()} (excluding held-out states)",
        "horizon": "next UTC day (persistence of a fire detected the previous day)",
        "models": {"B0": "seasonal baseline", "B1": "satellite-only logistic", "M2": "B1 + NASA POWER weather"},
    }
    (d / "scores_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {d / 'scores.parquet'}")


if __name__ == "__main__":
    main()
