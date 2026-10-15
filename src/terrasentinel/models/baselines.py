"""Baseline models for fire persistence (protocol levels B-null, B0, B1).

All models share one interface: fit(rows) then predict(rows) -> probability array, where
rows are the persistence dataset (cell_id, date, label, features...).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from terrasentinel.features.trailing import cutoff_for

_DAY = pd.Timedelta(days=1)


def _day_index(ts: pd.Series) -> np.ndarray:
    return ((cutoff_for(ts) - pd.Timestamp("1970-01-01", tz="UTC")) // _DAY).to_numpy(np.int64)


class PrevalenceBaseline:
    """B-null: predicts the training prevalence everywhere. Its PR-AUC equals the test prevalence."""

    name = "B_null_prevalence"

    def fit(self, rows: pd.DataFrame) -> PrevalenceBaseline:
        self.p_ = float(rows["label"].mean())
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        return np.full(len(rows), self.p_)


class SeasonalBaseline:
    """B0: fraction of days with a detection in the same cell, in a +/-k day window around the
    same day-of-year, in each of the previous `n_years` years. Uses prior years only.

    Years whose window starts before `history_start` are skipped (the archive does not cover them,
    so missing detections there are unknown, not zero). A Platt-scaled logistic regression on
    [seasonal_freq, has_history] turns the score into a probability.

    A year is approximated as 365 days; the +/-k window absorbs leap-day drift.
    """

    name = "B0_seasonal"

    def __init__(self, detections: pd.DataFrame, history_start: str, n_years: int = 5, half_window_days: int = 15):
        if not 0 <= half_window_days <= 60:
            raise ValueError("half_window_days must be in 0..60 so windows end well before the cutoff")
        self.n_years = n_years
        self.k = half_window_days
        self.history_start = int(_day_index(pd.Series([pd.Timestamp(history_start, tz="UTC")]))[0])
        d = pd.DataFrame({"cell_id": detections["cell_id"].to_numpy(),
                          "day": _day_index(detections["acq_datetime_utc"])}).drop_duplicates()
        self._days = {cid: np.sort(g["day"].to_numpy()) for cid, g in d.groupby("cell_id")}

    def seasonal_features(self, rows: pd.DataFrame) -> pd.DataFrame:
        day = _day_index(rows["date"])
        freq_sum = np.zeros(len(rows))
        n_valid = np.zeros(len(rows))
        for y in range(1, self.n_years + 1):
            lo, hi = day - 365 * y - self.k, day - 365 * y + self.k
            n_valid += lo >= self.history_start
        cells = pd.Series(rows["cell_id"].to_numpy())
        for cid, idx in cells.groupby(cells, sort=False).indices.items():
            days = self._days.get(cid)
            if days is None:
                continue
            d = day[idx]
            for y in range(1, self.n_years + 1):
                lo, hi = d - 365 * y - self.k, d - 365 * y + self.k
                cnt = np.searchsorted(days, hi, "right") - np.searchsorted(days, lo, "left")
                freq_sum[idx] += np.where(lo >= self.history_start, cnt, 0)
        width = 2 * self.k + 1
        freq = np.divide(freq_sum, n_valid * width, out=np.zeros(len(rows)), where=n_valid > 0)
        return pd.DataFrame({"seasonal_freq": freq, "has_history": (n_valid > 0).astype(float)}, index=rows.index)

    def fit(self, rows: pd.DataFrame) -> SeasonalBaseline:
        self.calibrator_ = LogisticRegression().fit(self.seasonal_features(rows), rows["label"])
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        return self.calibrator_.predict_proba(self.seasonal_features(rows))[:, 1]


class LogisticModel:
    """B1 (and later M2): regularised logistic regression on log1p-transformed non-negative features."""

    def __init__(self, features: list[str], name: str = "B1_satellite_only", C: float = 1.0):
        self.features = list(features)
        self.name = name
        self.C = C

    def fit(self, rows: pd.DataFrame) -> LogisticModel:
        missing = [f for f in self.features if f not in rows.columns]
        if missing:
            raise KeyError(f"missing feature columns {missing}")
        self.model_ = make_pipeline(
            FunctionTransformer(np.log1p), StandardScaler(), LogisticRegression(C=self.C, max_iter=2000)
        ).fit(rows[self.features].to_numpy(float), rows["label"].to_numpy())
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        return self.model_.predict_proba(rows[self.features].to_numpy(float))[:, 1]

    def coefficients(self) -> pd.Series:
        return pd.Series(self.model_[-1].coef_[0], index=self.features)
