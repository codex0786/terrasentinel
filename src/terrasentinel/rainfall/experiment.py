"""Workstream B v0 models and evaluation (docs/protocol_rainfall_v0.md)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from terrasentinel.evaluation.metrics import block_bootstrap_diff, block_ids, pr_auc, roc_auc
from terrasentinel.evaluation.splits import temporal_split
from terrasentinel.experiments.fire_persistence import protocol_locked
from terrasentinel.models.baselines import LogisticModel

RAW = ["mean_1d", "mean_3d"]
ANOMALY = ["frac_p99_1d", "frac_p99_3d", "max_3d"]


class StateMonthClimatology:
    """B0: P(event | state, calendar month) from training rows, add-one smoothing."""

    name = "B0_climatology"

    def fit(self, rows: pd.DataFrame) -> StateMonthClimatology:
        g = rows.groupby([rows["state"], rows["date"].dt.month])["label"].agg(["sum", "size"])
        self.rate_ = (g["sum"] + 1) / (g["size"] + 2)
        self.default_ = (rows["label"].sum() + 1) / (len(rows) + 2)
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        idx = pd.MultiIndex.from_arrays([rows["state"], rows["date"].dt.month])
        return self.rate_.reindex(idx).fillna(self.default_).to_numpy(float)


def add_b0_logit(rows: pd.DataFrame, b0: StateMonthClimatology) -> pd.DataFrame:
    p = np.clip(b0.predict(rows), 1e-6, 1 - 1e-6)
    return rows.assign(b0_logit=np.log(p / (1 - p)))


def run(rows: pd.DataFrame, *, include_test: bool = False, protocol_path: Path | None = None,
        n_boot: int = 2000, seed: int = 20261015) -> dict:
    if include_test and not (protocol_path and protocol_locked(protocol_path)):
        raise PermissionError("Test years are scored only after docs/protocol_rainfall_v0.md is LOCKED.")
    rows = rows.assign(set=temporal_split(rows["date"], "2019-12-31", "2020-12-31", 7))
    train = rows[rows["set"] == "train"]
    b0 = StateMonthClimatology().fit(train)
    rows = add_b0_logit(rows, b0)
    train = rows[rows["set"] == "train"]
    models = {
        "B0_climatology": b0,
        "B1_raw_rain": LogisticModel(RAW, name="B1_raw_rain").fit(train),
        "M1_anomaly": LogisticModel(RAW + ANOMALY + ["b0_logit"], name="M1_anomaly",
                                    log_features=RAW + ["max_3d"]).fit(train),
    }
    sets = ["val"] + (["test"] if include_test else [])
    metrics, comps, per_year = [], [], []
    for s in sets:
        df = rows[rows["set"] == s].copy()
        for name, m in models.items():
            df[name] = m.predict(df)
        y = df["label"].to_numpy()
        blocks = block_ids(df, region_col="state")
        for name in models:
            metrics.append({"set": s, "model": name, "n": len(df), "prevalence": y.mean(),
                            "roc_auc": roc_auc(y, df[name]), "pr_auc": pr_auc(y, df[name])})
        pairs = (("M1_anomaly", "B0_climatology"), ("M1_anomaly", "B1_raw_rain"), ("B1_raw_rain", "B0_climatology"))
        for a, b in pairs:
            d = block_bootstrap_diff(y, df[a], df[b], blocks, roc_auc, n_boot=n_boot, seed=seed)
            comps.append({"set": s, "comparison": f"{a.split('_')[0]} - {b.split('_')[0]} (ROC-AUC)", **d})
        for yr, g in df.groupby(df["date"].dt.year):
            per_year.append({"set": s, "year": yr, "n": len(g), "prevalence": g["label"].mean(),
                             **{f"{k.split('_')[0]}_pr_auc": pr_auc(g["label"], g[k]) for k in models},
                             **{f"{k.split('_')[0]}_roc_auc": roc_auc(g["label"], g[k]) for k in models}})
    counts = rows.groupby("set")["label"].agg(["size", "sum", "mean"])
    if not include_test:
        hidden = counts.index.isin(["test", "embargo"])   # embargo rows border the test period
        counts["sum"] = counts["sum"].astype("Int64").mask(hidden)
        counts["mean"] = counts["mean"].mask(hidden)
    return {"metrics": pd.DataFrame(metrics), "comparisons": pd.DataFrame(comps), "per_year": pd.DataFrame(per_year),
            "set_counts": counts, "coefficients": models["M1_anomaly"].coefficients()}
