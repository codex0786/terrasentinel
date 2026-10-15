"""B0 must use prior years only and must not treat pre-archive years as zero-fire years."""

import pandas as pd
import pytest

from terrasentinel.models.baselines import SeasonalBaseline
from tests.conftest import make_detections

ROW = pd.DataFrame({"cell_id": ["A"], "date": ["2024-04-01"]})


def feats(dets, history_start="2019-01-01", **kw):
    return SeasonalBaseline(make_detections(dets), history_start, **kw).seasonal_features(ROW).iloc[0]


def test_prior_year_counts():
    # 365 days before 2024-04-01 is 2023-04-02; window +/-1 day
    f = feats([("A", "2023-04-02T10:00"), ("A", "2023-04-03T10:00"), ("A", "2023-04-03T11:00")],
              n_years=1, half_window_days=1)
    assert f["seasonal_freq"] == pytest.approx(2 / 3) and f["has_history"] == 1


def test_current_and_future_detections_ignored():
    base = feats([("A", "2023-04-02T10:00")], n_years=2, half_window_days=5)
    injected = feats([("A", "2023-04-02T10:00"), ("A", "2024-03-31T10:00"), ("A", "2024-04-01T00:00"),
                      ("A", "2024-04-05T10:00"), ("A", "2025-04-01T10:00")], n_years=2, half_window_days=5)
    pd.testing.assert_series_equal(base, injected)


def test_years_before_archive_are_skipped_not_zero():
    f_full = feats([("A", "2023-04-02T10:00")], history_start="2015-01-01", n_years=3, half_window_days=0)
    f_short = feats([("A", "2023-04-02T10:00")], history_start="2023-01-01", n_years=3, half_window_days=0)
    assert f_full["seasonal_freq"] == pytest.approx(1 / 3)
    assert f_short["seasonal_freq"] == pytest.approx(1.0)


def test_no_history_flag():
    f = feats([], history_start="2024-01-01", n_years=2)
    assert f["has_history"] == 0 and f["seasonal_freq"] == 0
