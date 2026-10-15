"""Validate locked predictions against VIIRS burned area (VNP64A1), as pre-specified in
docs/validation_burned_area.md. Secondary, post-lock analysis.

    python pipelines/validate_burned_area.py
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir, load_yaml
from terrasentinel.evaluation.metrics import at_alert_budget, block_bootstrap_diff, block_ids, pr_auc
from terrasentinel.geospatial.grid import Grid
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.validation.vnp64a1 import PIX_M, read_tile

N_BOOT, SEED = 2000, 20261015
UNMAPPED_MAX = 0.5
PIX_KM2 = (PIX_M / 1000) ** 2          # sinusoidal grid is equal-area
DEG_KM = 111.195                        # km per degree on the MODIS sphere


def cell_pixel_count(lat: np.ndarray, res_deg: float) -> np.ndarray:
    return (res_deg * DEG_KM) ** 2 * np.cos(np.radians(lat)) / PIX_KM2


def kappa(a: np.ndarray, b: np.ndarray) -> float:
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def main() -> None:
    india = load_yaml("india.yaml")
    grid = Grid.from_config(india)
    archive = RawArchive(data_dir() / "raw")
    recs = {r.sha256: r for r in archive.records() if r.provider == "earthdata" and r.product == "VNP64A1"}

    burned_cells, unmapped_cells, n_tiles = [], [], 0
    for r in recs.values():
        b, u = read_tile(archive.read(r), r.request["filename"])
        n_tiles += 1
        if len(b):
            burned_cells.append(pd.DataFrame({"cell_id": grid.cell_id(b["lat"], b["lon"]),
                                              "date": b["date"]}).drop_duplicates())
        if len(u):
            unmapped_cells.append(pd.DataFrame({"cell_id": grid.cell_id(u["lat"], u["lon"]), "year": u["year"],
                                                "month": u["month"]}).value_counts().rename("n_unmapped").reset_index())
    burned = pd.concat(burned_cells, ignore_index=True).drop_duplicates()
    unmapped = (pd.concat(unmapped_cells, ignore_index=True)
                .groupby(["cell_id", "year", "month"], as_index=False)["n_unmapped"].sum())

    s = pd.read_parquet(data_dir() / "processed" / "fire_persistence_v0" / "scores.parquet")
    s = s[s["set"].isin(["test", "geo_test"])].copy()
    # Burned-area label: >=1 burned pixel in the cell dated D or D+1.
    pos = pd.concat([burned.assign(date=burned["date"]),
                     burned.assign(date=burned["date"] - pd.Timedelta(days=1))]).drop_duplicates()
    pos["ba_label"] = 1
    s = s.merge(pos, on=["cell_id", "date"], how="left")
    s["ba_label"] = s["ba_label"].fillna(0).astype(int)
    # Unknown: >= 50% of the cell's pixels unmapped in D's month.
    s["year"], s["month"] = s["date"].dt.year, s["date"].dt.month
    s = s.merge(unmapped, on=["cell_id", "year", "month"], how="left")
    s["unmapped_frac"] = s["n_unmapped"].fillna(0) / cell_pixel_count(s["lat"].to_numpy(), grid.resolution_deg)
    n_all = len(s)
    s = s[s["unmapped_frac"] < UNMAPPED_MAX].copy()

    rows, cmp = [], []
    for name, df in s.groupby("set"):
        y = df["ba_label"].to_numpy()
        prev = float(y.mean())
        blocks = block_ids(df)
        lift = block_bootstrap_diff(y, df["p_B1"], np.full(len(y), prev), blocks, pr_auc, n_boot=N_BOOT, seed=SEED)
        top = at_alert_budget(df.rename(columns={"label": "firms_label", "ba_label": "label"}), "p_B1",
                              fraction_per_day=0.10)
        rows.append({"set": name, "cell_days": len(df), "ba_prevalence": prev,
                     "firms_prevalence": df["label"].mean(),
                     **{f"{m}_pr_auc_vs_BA": pr_auc(y, df[f"p_{m}"]) for m in ("B0", "B1", "M2")},
                     "B1_lift_over_prev": lift["diff"], "lift_ci": f"[{lift['ci_low']:+.3f}, {lift['ci_high']:+.3f}]",
                     "top10_precision_vs_BA": top["precision"],
                     "kappa_FIRMS_vs_BA": kappa(df["label"].to_numpy(), y)})
        for a, b in (("B1", "B0"), ("M2", "B1")):
            d = block_bootstrap_diff(y, df[f"p_{a}"], df[f"p_{b}"], blocks, pr_auc, n_boot=N_BOOT, seed=SEED)
            cmp.append({"set": name, "comparison": f"{a} - {b} (PR-AUC vs BA)", "diff": d["diff"],
                        "ci": f"[{d['ci_low']:+.4f}, {d['ci_high']:+.4f}]"})
    agree = pd.crosstab(s["label"].rename("FIRMS next-day detection"), s["ba_label"].rename("BA burn D..D+1"))
    by_state = (s[s["set"] == "geo_test"].groupby("cell_region")
                .apply(lambda g: pd.Series({"cell_days": len(g), "ba_prev": g["ba_label"].mean(),
                                            "B1_pr_auc_vs_BA": pr_auc(g["ba_label"].to_numpy(), g["p_B1"])}),
                       include_groups=False))

    now = datetime.now(UTC)
    lines = [f"# Burned-area validation (VNP64A1) — {now:%Y-%m-%d %H:%M} UTC", "",
             "Pre-specified in `docs/validation_burned_area.md`; secondary, post-lock.", "",
             f"- VNP64A1 tiles read: {n_tiles}; burned cell-days: {len(burned):,}",
             f"- 2024 test cell-days: {n_all:,}; excluded as ≥50% unmapped: {n_all - len(s):,}; analysed: {len(s):,}",
             "", "## Primary", "", pd.DataFrame(rows).round(4).to_markdown(index=False), "",
             "## Model comparisons on the burned-area label", "", pd.DataFrame(cmp).round(4).to_markdown(index=False),
             "", "## Agreement: FIRMS label vs burned-area label (cell-days)", "", agree.to_markdown(), "",
             "## Held-out states", "", by_state.round(4).to_markdown(), ""]
    out = REPO_ROOT / "reports" / "experiment_summaries" / f"burned_area_validation_{now:%Y%m%dT%H%M}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"Wrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
