"""Rainfall v0 machinery on synthetic state-days: anomaly signal is recovered; test years stay gated."""

import numpy as np
import pandas as pd
import pytest

from terrasentinel.rainfall.experiment import run


def world(signal=True, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", "2023-12-31", freq="D", tz="UTC")
    rows = []
    for s in ["A", "B", "C", "D"]:
        monsoon = dates.month.isin([6, 7, 8, 9])
        rain = rng.gamma(0.5, 4, len(dates)) * np.where(monsoon, 4, 1)
        frac = np.clip(rng.beta(1, 30, len(dates)) + (rain > 30) * 0.2, 0, 1)
        logit = -4 + 1.5 * monsoon + (6 * frac if signal else 0)
        label = rng.random(len(dates)) < 1 / (1 + np.exp(-logit))
        rows.append(pd.DataFrame({"state": s, "date": dates, "mean_1d": rain, "mean_3d": rain * 2.5,
                                  "frac_p99_1d": frac, "frac_p99_3d": frac * 0.8, "max_3d": rain * 6,
                                  "label": label.astype(int)}))
    return pd.concat(rows, ignore_index=True)


def comp(res, s, name):
    return res["comparisons"].set_index(["set", "comparison"]).loc[(s, name)]


def test_anomaly_signal_recovered():
    res = run(world(), n_boot=200)
    assert comp(res, "val", "M1 - B0 (ROC-AUC)")["ci_low"] > 0


def test_no_signal_no_gain_over_climatology():
    res = run(world(signal=False, seed=3), n_boot=200)
    assert comp(res, "val", "M1 - B0 (ROC-AUC)")["ci_low"] < 0.02


def test_test_years_gated(tmp_path):
    p = tmp_path / "protocol.md"
    p.write_text("Status: **DRAFT**\n")
    with pytest.raises(PermissionError):
        run(world(), include_test=True, protocol_path=p, n_boot=50)
    res = run(world(), n_boot=50)
    assert pd.isna(res["set_counts"].loc["test", "mean"]) and "test" not in set(res["metrics"]["set"])
