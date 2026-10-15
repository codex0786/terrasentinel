"""Fit Workstream B v0 models on 2015-2019 and score validation (2020); test (2021-2023) only after lock.

    python pipelines/train_rainfall.py
    python pipelines/train_rainfall.py --evaluate-test     # requires docs/protocol_rainfall_v0.md LOCKED
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

import pandas as pd

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.rainfall.experiment import run


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--evaluate-test", action="store_true")
    args = p.parse_args()
    rows = pd.read_parquet(data_dir() / "processed" / "rainfall_v0" / "rows.parquet")
    res = run(rows, include_test=args.evaluate_test, protocol_path=REPO_ROOT / "docs" / "protocol_rainfall_v0.md")
    now = datetime.now(UTC)
    lines = [f"# rainfall_v0 ({now:%Y-%m-%d %H:%M} UTC)", "",
             f"Test years scored: **{'yes' if args.evaluate_test else 'no (development run)'}**", "",
             "## Rows per set", "", res["set_counts"].to_markdown(), "",
             "## Metrics", "", res["metrics"].round(4).to_markdown(index=False), "",
             "## Comparisons (block bootstrap, state x ISO week; M1 - B0 is the primary endpoint)", "",
             res["comparisons"].round(4).to_markdown(index=False), "",
             "## Per year", "", res["per_year"].round(4).to_markdown(index=False), "",
             "## M1 coefficients (standardised)", "", res["coefficients"].round(4).to_frame("coef").to_markdown(), "",
             "Labels are IMD-reported heavy-rain/flood events (IFI-Impacts); 0 = no reported event."]
    out = REPO_ROOT / "reports" / "experiment_summaries" / f"rainfall_v0_{now:%Y%m%dT%H%M}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"Wrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
