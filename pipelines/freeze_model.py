"""Freeze the locked B1 model to configs/models/b1_v0.json for deployment (no training data needed to score).

Fits the locked B1 specification on the study's training rows, exports it, verifies the frozen predictions
equal the saved study scores, and attaches plain-language risk bands with their observed persistence rates
on validation (2023) and the locked test (2024).

    python pipelines/freeze_model.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess

import numpy as np
import pandas as pd
import yaml

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.experiments.fire_persistence import assign_sets
from terrasentinel.models.baselines import LogisticModel
from terrasentinel.models.frozen import FrozenLogistic, export_logistic

EXPERIMENT = REPO_ROOT / "configs" / "experiments" / "fire_persistence_v0.yaml"
BANDS = [("low", 0.0, 0.3), ("medium", 0.3, 0.6), ("high", 0.6, 1.0001)]   # fixed cut-offs on P(persist)


def band_table(df: pd.DataFrame, p: np.ndarray) -> list[dict]:
    out = []
    for name, lo, hi in BANDS:
        m = (p >= lo) & (p < hi)
        out.append({"band": name, "p_min": lo, "p_max": min(hi, 1.0), "cell_days": int(m.sum()),
                    "share": float(m.mean()), "observed_rate": float(df.loc[m, "label"].mean()) if m.any() else None})
    return out


def main() -> None:
    cfg = yaml.safe_load(EXPERIMENT.read_text())
    rows_path = data_dir() / "processed" / cfg["experiment"] / "rows.parquet"
    rows = pd.read_parquet(rows_path)
    rows["set"] = assign_sets(rows, cfg["split"])
    b1 = LogisticModel(cfg["models"]["satellite_only_features"]).fit(rows[rows["set"] == "train"])

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                            text=True).stdout.strip()
    bands = {}
    for s in ("val", "test", "geo_test"):
        df = rows[rows["set"] == s]
        bands[s] = band_table(df, b1.predict(df))
    spec = export_logistic(b1, extra={
        "model_id": "fire_persistence_v0/B1",
        "horizon": "next UTC day; cells with a detection on the previous day",
        "trained_on": "2020-01-01..2022-12-31 (VIIRS S-NPP + NOAA-20 SP), held-out states excluded",
        "training_rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "experiment_config_sha256": hashlib.sha256(EXPERIMENT.read_bytes()).hexdigest(),
        "protocol_lock_commit": "e0c9385",
        "frozen_at_commit": commit,
        "bands": [{"band": n, "p_min": lo, "p_max": min(hi, 1.0)} for n, lo, hi in BANDS],
        "band_performance": bands,
    })
    frozen = FrozenLogistic(spec)
    scores = pd.read_parquet(data_dir() / "processed" / cfg["experiment"] / "scores.parquet")
    check = rows.merge(scores[["cell_id", "date", "p_B1"]], on=["cell_id", "date"])
    diff = np.abs(frozen.predict(check) - check["p_B1"].to_numpy(float)).max()
    if diff > 1e-6:                                   # saved scores are float32
        raise SystemExit(f"frozen model disagrees with study scores (max |diff| = {diff})")
    out = REPO_ROOT / "configs" / "models" / "b1_v0.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {out.relative_to(REPO_ROOT)} (sha256 {spec['sha256'][:16]}); max |diff| vs study = {diff:.2e}")
    for s, t in bands.items():
        print(s, [(b["band"], f"{b['share']:.0%} of cells", f"{b['observed_rate']:.0%} burned again") for b in t])


if __name__ == "__main__":
    main()
