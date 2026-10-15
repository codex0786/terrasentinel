"""Describe the built dataset to inform open protocol choices (alert budget, holdout states).

Only the TRAINING period is summarised for labels; validation/test rows are counted, never
inspected for outcomes. No model is fit.

    python pipelines/describe_dataset.py --experiment configs/experiments/fire_persistence_v0.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from terrasentinel.config import data_dir
from terrasentinel.evaluation.splits import temporal_split


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment", required=True, type=Path)
    args = p.parse_args()
    cfg = yaml.safe_load(args.experiment.read_text())
    rows = pd.read_parquet(data_dir() / "processed" / cfg["experiment"] / "rows.parquet")
    sp = cfg["split"]
    rows["set"] = temporal_split(rows["date"], sp["train_end"], sp["val_end"], sp["embargo_days"])

    print("Rows per set (counts only):")
    print(rows["set"].value_counts().to_string(), "\n")

    train = rows[rows["set"] == "train"]
    daily = train.groupby("date").agg(n=("label", "size"), prevalence=("label", "mean"))
    month = daily.groupby(daily.index.month).agg(days=("n", "size"), median_population=("n", "median"),
                                                 p90_population=("n", lambda s: s.quantile(0.9)),
                                                 mean_prevalence=("prevalence", "mean"))
    print(f"TRAIN {train['date'].min().date()}..{train['date'].max().date()}: {len(train):,} rows, "
          f"prevalence {train['label'].mean():.3f}")
    print("Daily eligible population, train:", daily["n"].describe(percentiles=[.1, .5, .9]).round(0).to_dict())
    print("\nBy calendar month (train):")
    print(month.round(3).to_string(), "\n")

    states = train.groupby("cell_region").agg(rows=("label", "size"), cells=("cell_id", "nunique"),
                                             prevalence=("label", "mean")).sort_values("rows", ascending=False)
    states["share"] = states["rows"] / states["rows"].sum()
    print("By state (train):")
    print(states.round(3).to_string())


if __name__ == "__main__":
    main()
