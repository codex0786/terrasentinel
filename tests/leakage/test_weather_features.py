"""Weather features for day D must use days <= D-1 only; climatology must predate all labels."""

import numpy as np
import pandas as pd
import pytest

from terrasentinel.features.weather import (
    _days_since_rain,
    build_weather_features,
    climatology,
    nearest_power_point,
    point_features,
)


def series(start="2019-01-01", end="2020-03-31", seed=0):
    d = pd.date_range(start, end, freq="D", tz="UTC")
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"date": d, "T2M_MAX": 30 + rng.normal(0, 2, len(d)), "RH2M": 50 + rng.normal(0, 5, len(d)),
                         "WS2M": 3 + rng.random(len(d)), "PRECTOTCORR": rng.gamma(0.5, 2, len(d))})


def test_future_weather_does_not_change_features():
    s = series()
    clim = climatology(s.assign(lat=0.0, lon=0.0), (2019, 2019)).drop(columns=["lat", "lon"])
    D = pd.Timestamp("2020-02-15", tz="UTC")
    base = point_features(s, clim).set_index("date").loc[D]
    s2 = s.copy()
    future = s2["date"] >= D
    s2.loc[future, ["T2M_MAX", "RH2M", "WS2M", "PRECTOTCORR"]] = [55.0, 1.0, 50.0, 900.0]
    injected = point_features(s2, clim).set_index("date").loc[D]
    pd.testing.assert_series_equal(base, injected)


def test_trailing_values_are_from_previous_days():
    s = series()
    f = point_features(s, None).set_index("date")
    D = pd.Timestamp("2020-02-15", tz="UTC")
    prev = s.set_index("date").loc[D - pd.Timedelta(days=3): D - pd.Timedelta(days=1)]
    assert f.loc[D, "t2m_max_3d"] == pytest.approx(prev["T2M_MAX"].mean())
    prev7 = s.set_index("date").loc[D - pd.Timedelta(days=7): D - pd.Timedelta(days=1)]
    assert f.loc[D, "precip_7d"] == pytest.approx(prev7["PRECTOTCORR"].sum())


def test_days_since_rain():
    assert list(_days_since_rain(np.array([0, 5, 0, 0, 2]))) == [60, 60, 1, 2, 3]


def test_climatology_uses_only_its_years():
    s = series("2018-01-01", "2020-12-31").assign(lat=0.0, lon=0.0)
    a = climatology(s, (2018, 2019))
    s2 = s.copy()
    s2.loc[s2["date"].dt.year == 2020, "T2M_MAX"] = 99.0
    b = climatology(s2, (2018, 2019))
    pd.testing.assert_frame_equal(a, b)


def test_climatology_must_predate_labels():
    s = series().assign(lat=0.0, lon=0.0)
    rows = pd.DataFrame({"cell_id": ["x"], "date": [pd.Timestamp("2020-02-15", tz="UTC")]})
    with pytest.raises(ValueError, match="before the first label day"):
        build_weather_features(s, rows, [0.0], [0.0], (2019, 2020), "2020-01-01")
    out = build_weather_features(s, rows, [0.1], [0.2], (2019, 2019), "2020-01-01")
    assert out["t2m_max_3d"].notna().all()


def test_nearest_power_point():
    lat, lon = nearest_power_point([28.61, 19.24], [77.21, 72.81])
    assert list(lat) == [28.5, 19.0] and list(lon) == [77.5, 72.5]
