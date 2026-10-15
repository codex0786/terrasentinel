"""End-to-end checks on synthetic worlds where the right answer is known."""

import pandas as pd
import pytest

from terrasentinel.experiments.fire_persistence import build_dataset, prepare_detections, run_baselines
from terrasentinel.geospatial.grid import Grid
from tests.geo_helpers import synthetic_fire_world, two_states

GRID = Grid(0.1, 68.0, 6.0)
BBOX = {"west": 68, "south": 6, "east": 98, "north": 38}
CFG = {
    "dataset": {"history_start": "2021-01-01"},
    "split": {"train_end": "2022-12-31", "val_end": "2023-06-30", "embargo_days": 7, "geographic_holdout": []},
    "models": {"seasonal": {"n_years": 2, "half_window_days": 15},
               "satellite_only_features": ["fire_count_1d", "fire_count_3d", "fire_count_7d",
                                           "frp_sum_1d", "days_since_last_fire"]},
    "evaluation": {"alert_budget": {"fraction_per_day": 0.1, "fixed_per_day": 5},
                   "bootstrap": {"n_boot": 300, "seed": 0}},
}


def make_rows(tmp_path, signal):
    boundary = two_states(tmp_path)
    det, info = prepare_detections(synthetic_fire_world(signal=signal), GRID, boundary, BBOX, 0.0)
    rows = build_dataset(det, GRID, boundary, "2021-02-01", "2023-12-31", [1, 3, 7], 365)
    return rows, det, info


@pytest.fixture(scope="module")
def signal_world(tmp_path_factory):
    return make_rows(tmp_path_factory.mktemp("sig"), signal=True)


def metric(res, model, eval_set="val", name="pr_auc"):
    m = res["metrics"]
    return m[(m["model"] == model) & (m["eval_set"] == eval_set)][name].iloc[0]


def test_dataset_is_well_formed(signal_world):
    rows, det, info = signal_world
    assert info["spatial_filter"] == "boundary" and info["rows_outside_boundary"] == 0
    assert set(rows["cell_region"]) == {"StateA", "StateB"}
    assert not rows.duplicated(["cell_id", "date"]).any()
    assert (rows["fire_count_1d"] >= 1).all()   # population: had a detection yesterday


def test_b1_recovers_planted_signal(signal_world):
    rows, det, _ = signal_world
    res = run_baselines(rows, det, CFG)
    prev = metric(res, "B_null_prevalence", name="prevalence")
    assert metric(res, "B1_satellite_only") > prev + 0.1
    assert metric(res, "B1_satellite_only", name="roc_auc") > 0.75
    assert metric(res, "B1_satellite_only", name="brier") < metric(res, "B_null_prevalence", name="brier")
    # B0 is informative here too (big-fire cells recur seasonally). Whether B1 beats B0 is an
    # empirical question, so it is reported with a CI rather than asserted.
    assert metric(res, "B0_seasonal") > prev
    assert metric(res, "B1_satellite_only", name="fixed5_saturated")  # ~5 rows/day vs budget 5
    assert 0 <= metric(res, "B1_satellite_only", name="top10%_precision") <= 1
    cmp = res["comparisons"].set_index("eval_set").loc["val"]
    assert cmp["ci_low"] <= cmp["diff"] <= cmp["ci_high"]


def test_no_signal_world_shows_no_gain(tmp_path):
    rows, det, _ = make_rows(tmp_path, signal=False)
    res = run_baselines(rows, det, CFG)
    prev = metric(res, "B_null_prevalence", name="prevalence")
    assert abs(metric(res, "B1_satellite_only") - prev) < 0.12
    assert abs(metric(res, "B1_satellite_only", name="roc_auc") - 0.5) < 0.1
    cmp = res["comparisons"].set_index("eval_set").loc["val"]
    assert cmp["ci_low"] < 0.05                  # no spurious, confidently-positive improvement


def test_test_set_locked(signal_world, tmp_path):
    rows, det, _ = signal_world
    protocol = tmp_path / "protocol.md"
    protocol.write_text("Status: **DRAFT")
    with pytest.raises(PermissionError):
        run_baselines(rows, det, CFG, include_test=True, protocol_path=protocol)
    protocol.write_text("Status: **LOCKED** (commit abc)")
    res = run_baselines(rows, det, CFG, include_test=True, protocol_path=protocol)
    assert "test" in set(res["metrics"]["eval_set"])
    assert "test" not in set(run_baselines(rows, det, CFG)["metrics"]["eval_set"])


def test_real_draft_protocol_is_not_locked():
    from terrasentinel.config import REPO_ROOT
    from terrasentinel.experiments.fire_persistence import protocol_locked
    # The draft *mentions* the lock marker; that must not count as locking it.
    assert "Status: **LOCKED" in (REPO_ROOT / "docs" / "research_protocol.md").read_text()
    assert not protocol_locked(REPO_ROOT / "docs" / "research_protocol.md")


def test_geographic_holdout_never_trains(signal_world):
    rows, det, _ = signal_world
    cfg = {**CFG, "split": {**CFG["split"], "geographic_holdout": ["StateB"]}}
    res = run_baselines(rows, det, cfg)
    counts = res["set_counts"]
    assert "geo_train_excluded" in counts.index and "geo_val" in counts.index
    scored = res["scored"]
    assert set(scored.loc[scored["set"] == "val", "cell_region"]) == {"StateA"}
    assert set(scored.loc[scored["set"] == "geo_val", "cell_region"]) == {"StateB"}


def test_missing_split_dates_rejected(signal_world):
    rows, det, _ = signal_world
    cfg = {**CFG, "split": {**CFG["split"], "train_end": None}}
    with pytest.raises(ValueError, match="train_end"):
        run_baselines(rows, det, cfg)


def test_seasonal_history_sources_restrict_b0(signal_world):
    rows, det, _ = signal_world
    cfg = {**CFG, "models": {**CFG["models"], "seasonal": {**CFG["models"]["seasonal"],
                                                           "history_sources": ["NOT_A_SOURCE"]}}}
    res = run_baselines(rows, det, cfg)
    b0 = res["scored"].loc[res["scored"]["set"] == "val", "B0_seasonal"]
    assert b0.nunique() == 1          # no usable history -> constant prediction


def test_dev_run_withholds_test_label_stats(signal_world):
    rows, det, _ = signal_world
    counts = run_baselines(rows, det, CFG)["set_counts"]
    assert counts.loc["test", "size"] > 0
    assert pd.isna(counts.loc["test", "sum"]) and pd.isna(counts.loc["test", "mean"])
    assert not pd.isna(counts.loc["train", "mean"])
