"""Rare-event evaluation: ranking, operational, and calibration metrics, plus a block bootstrap
for confidence intervals on model differences (rows within a block are correlated, so blocks,
not rows, are resampled)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

Metric = Callable[[np.ndarray, np.ndarray], float]


def _two_classes(y) -> bool:
    return len(np.unique(y)) == 2


def pr_auc(y, p) -> float:
    return float(average_precision_score(y, p)) if _two_classes(y) else float("nan")


def roc_auc(y, p) -> float:
    return float(roc_auc_score(y, p)) if _two_classes(y) else float("nan")


def brier(y, p) -> float:
    return float(brier_score_loss(y, p))


def at_alert_budget(df: pd.DataFrame, score: str, k_per_day: int | None = None, label: str = "label",
                    fraction_per_day: float | None = None) -> dict[str, float]:
    """Flag the top-scored cells each day: either a fixed k, or ceil(fraction x that day's eligible cells).
    Ties are broken by cell_id so results are deterministic."""
    if (k_per_day is None) == (fraction_per_day is None):
        raise ValueError("give exactly one of k_per_day or fraction_per_day")
    ranked = df.sort_values(["date", score, "cell_id"], ascending=[True, False, True])
    if k_per_day is not None:
        flagged = ranked.groupby("date", sort=False).head(k_per_day)
    else:
        if not 0 < fraction_per_day <= 1:
            raise ValueError("fraction_per_day must be in (0, 1]")
        rank = ranked.groupby("date", sort=False).cumcount()
        k = np.ceil(fraction_per_day * ranked.groupby("date", sort=False)["cell_id"].transform("size"))
        flagged = ranked[rank < k]
    tp = int(flagged[label].sum())
    total_pos = int(df[label].sum())
    return {
        "precision": tp / len(flagged) if len(flagged) else float("nan"),
        "recall": tp / total_pos if total_pos else float("nan"),
        "false_alerts_per_day": (len(flagged) - tp) / df["date"].nunique(),
    }


def calibration_table(y, p, n_bins: int = 10) -> tuple[pd.DataFrame, float]:
    """Uniform-width reliability table and expected calibration error (ECE)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    t = (pd.DataFrame({"bin": bins, "y": y, "p": p}).groupby("bin")
         .agg(n=("y", "size"), mean_pred=("p", "mean"), observed=("y", "mean")).reset_index())
    ece = float((t["n"] / len(y) * (t["mean_pred"] - t["observed"]).abs()).sum())
    return t, ece


def block_ids(df: pd.DataFrame, region_col: str = "cell_region") -> pd.Series:
    """Default block = region x ISO week."""
    iso = pd.to_datetime(df["date"], utc=True).dt.isocalendar()
    return df[region_col].astype(str) + "|" + iso["year"].astype(str) + "-W" + iso["week"].astype(str)


def block_bootstrap_diff(y, score_a, score_b, blocks, metric: Metric = pr_auc,
                         n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict[str, float]:
    """metric(a) - metric(b) with a percentile CI from resampling whole blocks."""
    y, a, b = (np.asarray(v) for v in (y, score_a, score_b))
    groups = list(pd.Series(np.arange(len(y))).groupby(np.asarray(blocks)).indices.values())
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if _two_classes(y[idx]):
            diffs.append(metric(y[idx], a[idx]) - metric(y[idx], b[idx]))
    diffs = np.asarray(diffs)
    return {
        "diff": metric(y, a) - metric(y, b),
        "ci_low": float(np.quantile(diffs, alpha / 2)) if len(diffs) else float("nan"),
        "ci_high": float(np.quantile(diffs, 1 - alpha / 2)) if len(diffs) else float("nan"),
        "n_boot_used": int(len(diffs)),
        "n_blocks": len(groups),
    }
