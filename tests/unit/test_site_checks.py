"""Each data-quality failure must block publishing; a healthy export must pass."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta

import pytest

from terrasentinel.config import REPO_ROOT, load_yaml

spec = importlib.util.spec_from_file_location("check_site_data", REPO_ROOT / "pipelines" / "check_site_data.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CFG = load_yaml("site_checks.yaml")
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def make(tmp, n_days=20, last_detections=900, as_of_hours=6, sensors=("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"),
         drop_day=None, schema="terrasentinel.site.v1"):
    d = tmp / "data"
    (d / "days").mkdir(parents=True)
    days = []
    for i in range(n_days):
        date = (NOW.date() - timedelta(days=n_days - 1 - i)).isoformat()
        final = i < n_days - 1
        det = last_detections if i == n_days - 2 else 1000
        days.append({"date": date, "detections": det, "cells": 300, "high": 50, "outcomes_final": final,
                     "unobserved": False, "high_burned_again": 0.7 if final else None})
        if date != drop_day:
            (d / "days" / f"{date}.json").write_text(json.dumps({"date": date, "cells": [], "detections": []}))
    as_of = (NOW - timedelta(hours=as_of_hours)).isoformat()
    (d / "meta.json").write_text(json.dumps({"schema": schema, "data_as_of_utc": as_of, "latest_day": days[-1]["date"],
                                             "latest_acquisition_utc": {s: as_of for s in sensors},
                                             "unobserved_days": []}))
    (d / "index.json").write_text(json.dumps({"days": days}))
    for name in ("states.json", "states.geojson", "results.json"):
        (d / name).write_text("{}")
    return d


def run(d):
    return mod.check(d, NOW, CFG)


def test_healthy_export_passes(tmp_path):
    errors, warnings, facts = run(make(tmp_path))
    assert errors == [] and facts["detection_ratio"] == pytest.approx(0.9)


@pytest.mark.parametrize("kwargs, needle", [
    ({"as_of_hours": 40}, "old"),
    ({"sensors": ("VIIRS_SNPP_NRT",)}, "VIIRS_NOAA20_NRT"),
    ({"last_detections": 20}, "possible data outage"),
    ({"last_detections": 50000}, "duplicated"),
    ({"n_days": 3}, "only 3 days"),
    ({"schema": "something.else"}, "schema"),
])
def test_failures_block(tmp_path, kwargs, needle):
    errors, _, _ = run(make(tmp_path, **kwargs))
    assert any(needle in e for e in errors), errors


def test_missing_day_file_blocks(tmp_path):
    day = (NOW.date() - timedelta(days=5)).isoformat()
    errors, _, _ = run(make(tmp_path, drop_day=day))
    assert any(day in e for e in errors)


def test_malformed_json_blocks(tmp_path):
    d = make(tmp_path)
    (d / "states.json").write_text("{not json")
    errors, _, _ = run(d)
    assert any("not valid JSON" in e for e in errors)


def test_small_baseline_skips_ratio_with_warning(tmp_path):
    d = make(tmp_path)
    idx = json.loads((d / "index.json").read_text())
    for x in idx["days"]:
        x["detections"] = 10
    (d / "index.json").write_text(json.dumps(idx))
    errors, warnings, _ = run(d)
    assert errors == [] and any("ratio checks skipped" in w for w in warnings)
