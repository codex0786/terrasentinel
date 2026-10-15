import numpy as np
import pandas as pd
import pytest

from terrasentinel.rainfall.core import event_state_days, monthly_thresholds, state_features, three_day_totals


def test_three_day_totals_use_prior_days():
    d = np.array([[1.0], [2.0], [3.0], [4.0]])
    t = three_day_totals(d, prev2=np.array([[10.0], [20.0]]))
    assert t[:, 0].tolist() == [31.0, 23.0, 6.0, 9.0]
    assert np.isnan(three_day_totals(d)[0, 0])          # unknown history -> NaN, not 0


def test_monthly_thresholds_pool_neighbouring_months():
    months = np.array([12, 1, 2, 6])
    v = np.array([[100.0], [1.0], [1.0], [500.0]])
    thr = monthly_thresholds(v, months, q=100)
    assert thr[0, 0] == 100.0      # Jan pools Dec, Jan, Feb
    assert thr[5, 0] == 500.0      # Jun pools May-Jul
    assert np.isnan(thr[8, 0])     # Sep: no data -> NaN


def test_state_features():
    dates = pd.date_range("2020-07-01", periods=2, tz="UTC")
    daily = np.array([[0.0, 10.0, 50.0], [0.0, 0.0, 0.0]])
    three = daily.copy()
    thr = np.full((12, 3), 20.0, dtype=np.float32)
    f = state_features(daily, three, np.array([7, 7]), thr, thr, np.array(["A", "A", "B"]), dates)
    a = f[f.state == "A"].set_index("date")
    assert a["mean_1d"].iloc[0] == 5.0 and a["frac_p99_1d"].iloc[0] == 0.0
    b = f[f.state == "B"].set_index("date")
    assert b["frac_p99_1d"].iloc[0] == 1.0 and b["max_3d"].iloc[0] == 50.0


def events(rows):
    return pd.DataFrame(rows, columns=["Start Date", "End Date", "Main Cause", "State"])


def test_event_state_days_filters_and_maps():
    ev = events([
        ("01-07-2020 00:00", "02-07-2020 00:00", "Heavy Rains & Floods", "Assam, Jammu & Kashmir"),
        ("05-07-2020 00:00", "05-07-2020 00:00", "landslide", "Assam"),
        ("01-07-2020 00:00", "30-09-2020 00:00", "flood", "Bihar"),            # > 30 days: dropped
        ("10-07-2020 00:00", "10-07-2020 00:00", "heavy rains", "Atlantis"),
    ])
    pos, rep = event_state_days(ev, ["Assam", "Jammu and Kashmīr", "Bihār"], {"Jammu & Kashmir": "Jammu and Kashmīr"},
                                "2020-01-01", "2020-12-31")
    assert sorted(pos["state"].unique()) == ["Assam", "Jammu and Kashmīr"] and len(pos) == 4
    assert rep["dropped_longer_than_30d"] == 1 and rep["unmatched_state_tokens"] == ["Atlantis"]


@pytest.mark.parametrize("window", [("2020-07-02", "2020-07-02")])
def test_event_clipped_to_window(window):
    ev = events([("01-07-2020 00:00", "03-07-2020 00:00", "flood", "Assam")])
    pos, _ = event_state_days(ev, ["Assam"], {}, *window)
    assert len(pos) == 1
