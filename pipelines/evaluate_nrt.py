"""Evaluate the locked B1 model on near-real-time data (final labels only) and compare it with the
same calendar months of the 2024 science-quality test set.

This is a secondary, post-lock analysis: it was not pre-registered and does not change the v0
conclusion. Differences mix the NRT-vs-SP data product, the 3 h publication lag, and year (2026 vs 2024).

    python pipelines/evaluate_nrt.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.evaluation.metrics import at_alert_budget, block_bootstrap_diff, block_ids, brier, pr_auc

N_BOOT, SEED = 2000, 20261015


def summarize(df: pd.DataFrame, name: str) -> dict:
    y, p = df["label"].to_numpy(int), df["p_B1"].to_numpy(float)
    prev = float(y.mean())
    lift = block_bootstrap_diff(y, p, np.full(len(y), prev), block_ids(df), pr_auc, n_boot=N_BOOT, seed=SEED)
    top = at_alert_budget(df, "p_B1", fraction_per_day=0.10)
    return {"set": name, "days": df["date"].nunique(), "cell_days": len(df), "prevalence": prev,
            "B1_pr_auc": pr_auc(y, p), "lift_over_prevalence": lift["diff"],
            "lift_ci": f"[{lift['ci_low']:+.3f}, {lift['ci_high']:+.3f}]",
            "top10_precision": top["precision"], "brier": brier(y, p)}


def main() -> None:
    live = pd.read_parquet(data_dir() / "live" / "live_scores.parquet")
    meta = json.loads((data_dir() / "live" / "live_meta.json").read_text())
    nrt = live[live["label_final"]].copy()
    nrt["label"] = nrt["label"].astype(int)
    lo, hi = nrt["date"].min(), nrt["date"].max()

    # Same calendar-day window in 2024, so the seasonal mix matches (e.g. a partial October).
    sp = pd.read_parquet(data_dir() / "processed" / "fire_persistence_v0" / "scores.parquet")
    lo24, hi24 = lo.replace(year=2024), hi.replace(year=2024)
    sp = sp[(sp["set"] == "test") & sp["date"].between(lo24, hi24)].copy()

    res = pd.DataFrame([summarize(nrt, f"NRT {lo.date()}..{hi.date()}"),
                        summarize(sp, f"SP 2024 test {lo24.date()}..{hi24.date()}")])
    by_month = []
    for label, df in (("NRT 2026", nrt), ("SP 2024", sp)):
        for m, g in df.groupby(df["date"].dt.month):
            by_month.append({"data": label, "month": m, "cell_days": len(g), "prevalence": g["label"].mean(),
                             "B1_pr_auc": pr_auc(g["label"].to_numpy(int), g["p_B1"].to_numpy(float))})
    by_month = pd.DataFrame(by_month).pivot(index="month", columns="data")

    now = datetime.now(UTC)
    lines = [f"# B1 on near-real-time data — {now:%Y-%m-%d %H:%M} UTC", "",
             "Secondary, post-lock analysis (not pre-registered). Labels are final NRT detections; "
             f"features use a {meta['nrt_lag_hours']} h publication lag. Unobserved days excluded: "
             f"{meta['unobserved_days']}.", "",
             res.round(4).to_markdown(index=False), "", "## By month", "", by_month.round(3).to_markdown(), "",
             "Lift = B1 PR-AUC − prevalence (PR-AUC of a no-skill model), 95% block-bootstrap CI.",
             "Differences between rows mix product (NRT vs SP), lag, and year; they are descriptive."]
    out = REPO_ROOT / "reports" / "experiment_summaries" / f"nrt_evaluation_{now:%Y%m%dT%H%M}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
