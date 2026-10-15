"""Future-data injection tests: adding observations at or after the cutoff must not
change any feature, and late-available observations must stay invisible."""

import pandas as pd
import pytest

from terrasentinel.evaluation.splits import temporal_split
from terrasentinel.features.trailing import build_trailing_features
from terrasentinel.labels.persistence import build_persistence_rows
from tests.conftest import make_detections

WINDOWS = [1, 3, 7]
ROWS = pd.DataFrame({"cell_id": ["A", "A", "B"], "date": ["2024-03-10", "2024-03-12", "2024-03-10"]})
PAST = [("A", "2024-03-09T08:00"), ("A", "2024-03-05T08:00"), ("B", "2024-03-01T08:00")]


def feats(det):
    return build_trailing_features(det, ROWS, WINDOWS).drop(columns=["date"])


def test_injecting_future_detections_changes_nothing():
    base = feats(make_detections(PAST))
    future = PAST + [
        ("A", "2024-03-10T00:00"),   # exactly at the cutoff for row 0
        ("A", "2024-03-12T13:00"),
        ("B", "2024-03-10T23:59"),
        ("A", "2025-01-01T00:00"),
    ]
    injected = feats(make_detections(future))
    # Row 1 (A, 03-12) legitimately sees the 03-10 detection; check rows whose window excludes it.
    pd.testing.assert_frame_equal(base.iloc[[0, 2]], injected.iloc[[0, 2]])


def test_boundary_detection_belongs_to_label_day_not_features():
    det = make_detections([("A", "2024-03-10T00:00")])
    out = build_trailing_features(det, ROWS.iloc[[0]], WINDOWS)
    assert out["fire_count_1d"].iloc[0] == 0
    assert out["days_since_last_fire"].iloc[0] == 365


def test_window_edges():
    det = make_detections([("A", "2024-03-09T00:00"), ("A", "2024-03-08T23:59")])
    out = build_trailing_features(det, ROWS.iloc[[0]], WINDOWS)
    assert out["fire_count_1d"].iloc[0] == 1   # [03-09 00:00, 03-10 00:00)
    assert out["fire_count_3d"].iloc[0] == 2
    assert out["days_since_last_fire"].iloc[0] == pytest.approx(1.0)


def test_publication_lag_hides_late_observations():
    det = make_detections([("A", "2024-03-09T22:00")], lag_hours=3)  # available 03-10 01:00
    out = build_trailing_features(det, ROWS.iloc[[0]], WINDOWS)
    assert out["fire_count_1d"].iloc[0] == 0


def test_label_population_respects_availability():
    # Acquired late on D-1 but published after the D cutoff: not knowable at prediction time.
    det = make_detections([("A", "2024-03-09T22:00"), ("B", "2024-03-09T10:00")], lag_hours=3)
    rows = build_persistence_rows(det, "2024-03-10", "2024-03-10")
    assert list(rows["cell_id"]) == ["B"]


def test_persistence_labels():
    det = make_detections([("A", "2024-03-09T10:00"), ("A", "2024-03-10T10:00"),
                           ("B", "2024-03-09T10:00")])
    rows = build_persistence_rows(det, "2024-03-10", "2024-03-10")
    assert rows.set_index("cell_id")["label"].to_dict() == {"A": 1, "B": 0}


def test_temporal_split_embargo():
    dates = pd.Series(pd.date_range("2024-01-01", "2024-01-20", freq="D"))
    s = temporal_split(dates, train_end="2024-01-05", val_end="2024-01-12", embargo_days=2)
    d = pd.to_datetime(dates)
    assert d[s == "train"].max() == pd.Timestamp("2024-01-05")
    assert d[s == "val"].min() == pd.Timestamp("2024-01-08")
    assert d[s == "test"].min() == pd.Timestamp("2024-01-15")
    assert (s == "embargo").sum() == 4


def test_outage_days_are_not_labelled_as_fire_stopped():
    from terrasentinel.labels.persistence import find_unobserved_days
    det = make_detections([("A", "2024-03-09T10:00"), ("B", "2024-03-09T10:00"), ("A", "2024-03-11T10:00")])
    unobserved = find_unobserved_days(det, "2024-03-10", "2024-03-11")
    assert [d.date().isoformat() for d in unobserved] == ["2024-03-10"]   # nothing seen anywhere that day
    rows = build_persistence_rows(det, "2024-03-10", "2024-03-11", unobserved)
    assert rows.empty                                                      # no false zeros on 03-10


def test_known_outages_merge_with_detected_gaps():
    from terrasentinel.labels.persistence import find_unobserved_days
    det = make_detections([("A", f"2024-03-{d:02d}T10:00") for d in range(1, 11) if d != 4])
    known = [("2024-03-07", "2024-03-08"), ("2024-04-01", "2024-04-02")]
    got = find_unobserved_days(det, "2024-03-01", "2024-03-10", known)
    assert [d.day for d in got] == [4, 7, 8]
