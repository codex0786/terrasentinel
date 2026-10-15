"""Fit B-null, B0 (seasonal) and B1 (satellite-only) on the training period and score validation sets.

    python pipelines/train_baselines.py --experiment configs/experiments/fire_persistence_v0.yaml
    python pipelines/train_baselines.py --experiment ... --evaluate-test   # only once the protocol is LOCKED
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.experiments.fire_persistence import run_baselines


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment", required=True, type=Path)
    p.add_argument("--evaluate-test", action="store_true")
    args = p.parse_args()

    cfg = yaml.safe_load(args.experiment.read_text())
    ds_dir = data_dir() / "processed" / cfg["experiment"]
    rows = pd.read_parquet(ds_dir / "rows.parquet")
    det = pd.read_parquet(ds_dir / "detections.parquet")
    res = run_baselines(rows, det, cfg, include_test=args.evaluate_test,
                        protocol_path=REPO_ROOT / "docs" / "research_protocol.md")

    now = datetime.now(UTC)
    lines = [
        f"# {cfg['experiment']}: baselines ({now:%Y-%m-%d %H:%M} UTC)", "",
        f"Test sets scored: **{'yes' if args.evaluate_test else 'no (development run)'}**", "",
        "## Rows per set", "", res["set_counts"].to_markdown(), "",
        "## Metrics", "", res["metrics"].round(4).to_markdown(index=False), "",
        "## Model comparisons (block bootstrap, region x ISO week; M2 - B1 is the pre-registered primary)", "",
        res["comparisons"].round(4).to_markdown(index=False), "",
        "## Logistic coefficients (standardised; counts/precip/dry-days log1p)", "",
        pd.DataFrame(res["coefficients"]).round(4).to_markdown(), "",
        "Labels are future *detections*, not verified fire (see docs/limitations.md).",
    ]
    out = REPO_ROOT / "reports" / "experiment_summaries" / f"{cfg['experiment']}_{now:%Y%m%dT%H%M}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
