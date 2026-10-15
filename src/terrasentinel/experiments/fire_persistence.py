"""Fire-persistence experiment: dataset assembly and baseline evaluation.

The test period (and the geographic holdout during the test period) is only scored when the
research protocol is marked LOCKED. Development runs score validation sets only.
"""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from terrasentinel.evaluation.metrics import (
    at_alert_budget,
    block_bootstrap_diff,
    block_ids,
    brier,
    calibration_table,
    pr_auc,
    roc_auc,
)
from terrasentinel.evaluation.splits import geographic_holdout, temporal_split
from terrasentinel.features.trailing import attach_availability, build_trailing_features
from terrasentinel.geospatial.boundary import cell_regions, clip_detections
from terrasentinel.geospatial.grid import Grid, in_bbox
from terrasentinel.labels.persistence import build_persistence_rows, filter_qualifying
from terrasentinel.models.baselines import LogisticModel, PrevalenceBaseline, SeasonalBaseline

LOCK_LINE = re.compile(r"^Status: \*\*LOCKED\b", re.MULTILINE)


def protocol_locked(path: Path) -> bool:
    """True only if a line *starts* with 'Status: **LOCKED' (mentions elsewhere in the text don't count)."""
    return LOCK_LINE.search(Path(path).read_text()) is not None


def prepare_detections(det: pd.DataFrame, grid: Grid, boundary: gpd.GeoDataFrame | None,
                       bbox: dict, lag_hours: float, allowed_classes=("nominal", "high")
                       ) -> tuple[pd.DataFrame, dict]:
    info: dict = {"rows_normalized": len(det)}
    det = det[in_bbox(det, bbox)]
    info["rows_in_bbox"] = len(det)
    if boundary is not None:
        det, rep = clip_detections(det, boundary, grid)
        info.update(spatial_filter="boundary", rows_in_boundary=rep.rows_inside, rows_outside_boundary=rep.rows_outside)
    else:
        det = det.assign(region="bbox_only")
        info["spatial_filter"] = "bbox_only (NOT India-clipped; not reportable)"
    det = filter_qualifying(det, allowed_classes)
    info["rows_qualifying"] = len(det)
    det = det.assign(cell_id=grid.cell_id(det["latitude"], det["longitude"]))
    return attach_availability(det, lag_hours).reset_index(drop=True), info


def build_dataset(det: pd.DataFrame, grid: Grid, boundary: gpd.GeoDataFrame | None,
                  start: str, end: str, windows: list[int], days_since_cap: float,
                  unobserved_days=()) -> pd.DataFrame:
    """det: output of prepare_detections. Returns one row per (cell, day) in the persistence population.
    unobserved_days (see labels.persistence.find_unobserved_days) are excluded as label days."""
    rows = build_persistence_rows(det, start, end, unobserved_days)
    rows = build_trailing_features(det, rows, windows, days_since_cap)
    if boundary is not None:
        regions = cell_regions(grid, rows["cell_id"], boundary)
        # Border cells whose centre falls outside the boundary take their detections' majority region.
        fallback = det.groupby("cell_id")["region"].agg(lambda s: s.mode().iloc[0])
        regions["cell_region"] = regions["cell_region"].fillna(regions["cell_id"].map(fallback))
        rows = rows.merge(regions, on="cell_id", how="left")
    else:
        rows["cell_region"] = "bbox_only"
    return rows


def assign_sets(rows: pd.DataFrame, split_cfg: dict) -> pd.Series:
    """train / val / geo_val / test / geo_test / embargo / geo_train_excluded."""
    t = temporal_split(rows["date"], split_cfg["train_end"], split_cfg["val_end"], split_cfg["embargo_days"])
    holdout = split_cfg.get("geographic_holdout") or []
    geo = geographic_holdout(rows["cell_region"], holdout) if holdout else pd.Series(False, index=rows.index)
    s = t.copy()
    s[geo & (t == "train")] = "geo_train_excluded"  # held-out regions never enter training
    s[geo & (t == "val")] = "geo_val"
    s[geo & (t == "test")] = "geo_test"
    return s


def evaluate_scores(df: pd.DataFrame, score_cols: list[str], budget: dict) -> pd.DataFrame:
    """budget: {"fraction_per_day": f (primary), "fixed_per_day": k (secondary, optional)}."""
    out = []
    frac, fixed = budget.get("fraction_per_day"), budget.get("fixed_per_day")
    # A fixed budget that flags most rows cannot separate models.
    fixed_flagged = (float(df.groupby("date").size().clip(upper=fixed).sum() / len(df))
                     if fixed and len(df) else None)
    for col in score_cols:
        y, p = df["label"].to_numpy(), df[col].to_numpy()
        _, ece = calibration_table(y, p)
        row = {"model": col, "n": len(df), "prevalence": float(y.mean()) if len(y) else np.nan,
               "pr_auc": pr_auc(y, p), "roc_auc": roc_auc(y, p), "brier": brier(y, p), "ece": ece}
        if frac:
            row |= {f"top{frac:.0%}_{k}": v for k, v in at_alert_budget(df, col, fraction_per_day=frac).items()}
        if fixed:
            row |= {f"fixed{fixed}_{k}": v for k, v in at_alert_budget(df, col, k_per_day=fixed).items()}
            row |= {f"fixed{fixed}_flagged_frac": fixed_flagged, f"fixed{fixed}_saturated": fixed_flagged > 0.5}
        out.append(row)
    return pd.DataFrame(out)


def _set_counts(rows: pd.DataFrame, include_test: bool) -> pd.DataFrame:
    """Row counts per set; label statistics for test sets are withheld until the protocol is locked."""
    counts = rows.groupby("set")["label"].agg(["size", "sum", "mean"])
    if not include_test:
        hidden = counts.index.isin(["test", "geo_test"])
        counts["sum"] = counts["sum"].astype("Int64").mask(hidden)
        counts["mean"] = counts["mean"].mask(hidden)
    return counts


def run_baselines(rows: pd.DataFrame, det: pd.DataFrame, cfg: dict, *, include_test: bool = False,
                  protocol_path: Path | None = None) -> dict:
    if include_test and not (protocol_path and protocol_locked(protocol_path)):
        raise PermissionError("Test sets are scored only after docs/research_protocol.md is marked LOCKED.")
    for key in ("train_end", "val_end"):
        if not cfg["split"].get(key):
            raise ValueError(f"split.{key} is not set in the experiment config")

    rows = rows.assign(set=assign_sets(rows, cfg["split"]))
    train = rows[rows["set"] == "train"]
    if train["label"].nunique() < 2:
        raise ValueError("training set needs both classes")

    m = cfg["models"]
    seasonal = dict(m["seasonal"])
    history_sources = seasonal.pop("history_sources", None)
    # B0's history must come from sensors with consistent coverage over all history years.
    hist = det if not history_sources else det[det["source"].isin(history_sources)]
    models = [
        PrevalenceBaseline(),
        SeasonalBaseline(hist, cfg["dataset"]["history_start"], **seasonal),
        LogisticModel(m["satellite_only_features"]),
    ]
    for model in models:
        model.fit(train)

    eval_sets = ["val", "geo_val"] + (["test", "geo_test"] if include_test else [])
    budget = cfg["evaluation"]["alert_budget"]
    bs = cfg["evaluation"]["bootstrap"]
    results, comparisons, scored = [], [], []
    for name in eval_sets:
        df = rows[rows["set"] == name].copy()
        if df.empty:
            continue
        for model in models:
            df[model.name] = model.predict(df)
        metrics = evaluate_scores(df, [mm.name for mm in models], budget).assign(eval_set=name)
        results.append(metrics)
        cmp = block_bootstrap_diff(df["label"], df["B1_satellite_only"], df["B0_seasonal"], block_ids(df),
                                   pr_auc, n_boot=bs["n_boot"], seed=bs["seed"])
        comparisons.append({"eval_set": name, "comparison": "B1 - B0 (pr_auc)", **cmp})
        scored.append(df)

    return {
        "metrics": pd.concat(results, ignore_index=True) if results else pd.DataFrame(),
        "comparisons": pd.DataFrame(comparisons),
        "set_counts": _set_counts(rows, include_test),
        "b1_coefficients": models[2].coefficients(),
        "scored": pd.concat(scored, ignore_index=True) if scored else pd.DataFrame(),
    }
