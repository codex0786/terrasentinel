import numpy as np
import pandas as pd
import pytest

from terrasentinel.evaluation.metrics import at_alert_budget, block_bootstrap_diff, calibration_table, pr_auc
from terrasentinel.evaluation.splits import geographic_holdout


def test_pr_auc_perfect_and_single_class():
    assert pr_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert np.isnan(pr_auc([0, 0], [0.1, 0.2]))


def test_alert_budget_hand_example():
    df = pd.DataFrame({
        "date": ["d1"] * 3 + ["d2"] * 3,
        "cell_id": list("abcabc"),
        "label": [1, 0, 0, 0, 1, 1],
        "s": [0.9, 0.8, 0.1, 0.9, 0.5, 0.5],
    })
    m = at_alert_budget(df, "s", 1)
    # d1 flags a (TP); d2 flags a (FP)
    assert m["precision"] == 0.5 and m["recall"] == pytest.approx(1 / 3) and m["false_alerts_per_day"] == 0.5


def test_alert_budget_ties_are_deterministic():
    df = pd.DataFrame({"date": ["d"] * 2, "cell_id": ["b", "a"], "label": [0, 1], "s": [0.5, 0.5]})
    assert at_alert_budget(df, "s", 1)["precision"] == 1.0   # 'a' wins the tie


def test_calibration_perfect():
    p = np.repeat([0.05, 0.55], 1000)
    y = np.concatenate([np.r_[np.ones(50), np.zeros(950)], np.r_[np.ones(550), np.zeros(450)]])
    _, ece = calibration_table(y, p)
    assert ece == pytest.approx(0, abs=1e-12)


def test_bootstrap_identical_models_and_determinism():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 400)
    a = rng.random(400)
    blocks = np.repeat(np.arange(40), 10)
    r = block_bootstrap_diff(y, a, a, blocks, n_boot=200)
    assert r["diff"] == 0 and r["ci_low"] == 0 and r["ci_high"] == 0 and r["n_blocks"] == 40
    b = rng.random(400)
    assert block_bootstrap_diff(y, a, b, blocks, n_boot=200, seed=3) == block_bootstrap_diff(
        y, a, b, blocks, n_boot=200, seed=3)


def test_bootstrap_detects_real_difference():
    rng = np.random.default_rng(2)
    y = rng.integers(0, 2, 2000)
    good = y + rng.normal(0, 0.5, 2000)
    noise = rng.random(2000)
    r = block_bootstrap_diff(y, good, noise, np.repeat(np.arange(100), 20), n_boot=300)
    assert r["ci_low"] > 0


def test_geographic_holdout_unknown_region():
    regions = pd.Series(["A", "B", None])
    assert list(geographic_holdout(regions, ["A"])) == [True, False, False]
    with pytest.raises(ValueError):
        geographic_holdout(regions, ["Z"])


def test_fractional_budget_scales_with_daily_population():
    df = pd.DataFrame({
        "date": ["d1"] * 10 + ["d2"] * 3,
        "cell_id": [f"c{i}" for i in range(13)],
        "label": [1] + [0] * 9 + [0, 0, 1],
        "s": list(range(10, 0, -1)) + [3, 2, 1],
    })
    m = at_alert_budget(df, "s", fraction_per_day=0.1)
    # d1: ceil(1.0)=1 flagged (TP); d2: ceil(0.3)=1 flagged (FP)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    with pytest.raises(ValueError):
        at_alert_budget(df, "s", k_per_day=1, fraction_per_day=0.1)
