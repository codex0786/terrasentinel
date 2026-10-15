"""The exporter must produce the JSON contract the frontend reads (terrasentinel.site.v1)."""

import importlib.util
import json
import sys

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from terrasentinel.config import REPO_ROOT, load_yaml

spec = importlib.util.spec_from_file_location("export_site_data", REPO_ROOT / "pipelines" / "export_site_data.py")
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def fake_live(tmp):
    live = tmp / "live"
    live.mkdir(parents=True)
    days = pd.to_datetime(["2026-10-14", "2026-10-15"], utc=True)
    pd.DataFrame({
        "cell_id": ["r1_c1", "r2_c2", "r1_c1"], "date": [days[0], days[0], days[1]],
        "cell_region": ["StateA", "StateB", "StateA"], "lat": [20.05, 21.05, 20.05], "lon": [80.05, 81.05, 80.05],
        "p_B1": [0.8, 0.2, 0.5], "fire_count_1d": [5, 1, 3], "frp_sum_1d": [20.0, 2.0, 9.0],
        "label": pd.array([1, 0, pd.NA], dtype="Int64"), "label_final": [True, True, False],
    }).to_parquet(live / "live_scores.parquet")
    pd.DataFrame({"latitude": [20.01], "longitude": [80.02], "acq_datetime_utc": [days[1] + pd.Timedelta(hours=8)],
                  "frp": [4.5], "satellite": ["N"], "region": ["StateA"]}).to_parquet(live / "live_detections.parquet")
    (live / "live_meta.json").write_text(json.dumps({
        "run_at_utc": "2026-10-15T10:00:00+00:00", "scored_days": ["2026-10-14", "2026-10-15"],
        "latest_acquisition_utc": {"VIIRS_SNPP_NRT": "2026-10-15T08:00:00+00:00"}, "unobserved_days": []}))
    rel = load_yaml("india.yaml")["region"]["boundary_file"]
    path = tmp / rel
    path.parent.mkdir(parents=True)
    gpd.GeoDataFrame({"shapeName": ["StateA", "StateB"]}, geometry=[box(79, 19, 81, 21), box(81, 20, 83, 22)],
                     crs="EPSG:4326").to_file(path, driver="GeoJSON")


def test_export_contract(tmp_path, monkeypatch):
    fake_live(tmp_path)
    monkeypatch.setenv("TERRASENTINEL_DATA_DIR", str(tmp_path))
    out = tmp_path / "site"
    monkeypatch.setattr(sys, "argv", ["export", "--out", str(out)])
    export.main()

    meta = json.loads((out / "meta.json").read_text())
    assert meta["schema"] == "terrasentinel.site.v1" and meta["latest_day"] == "2026-10-15"
    assert {"id", "sha256", "bands"} <= set(meta["model"]) and "Not an official warning" in meta["disclaimer"]

    index = json.loads((out / "index.json").read_text())["days"]
    assert [d["date"] for d in index] == ["2026-10-14", "2026-10-15"]
    assert index[0]["outcomes_final"] and index[0]["high_burned_again"] == 1.0 and not index[1]["outcomes_final"]

    day = json.loads((out / "days" / "2026-10-15.json").read_text())
    assert day["cell_fields"] == ["id", "lat", "lon", "state", "p", "band", "detections_prev_day", "frp_prev_day",
                                  "burned_again"]
    assert day["cells"][0][5] == "medium" and day["cells"][0][8] is None        # pending outcome stays null
    assert day["detections"][0][2] == "0800"

    first = json.loads((out / "days" / "2026-10-14.json").read_text())
    assert [c[5] for c in first["cells"]] == ["high", "low"]                    # sorted by p, banded

    states = json.loads((out / "states.json").read_text())
    assert states["fields"] == ["date", "detections", "cells", "high"] and "StateA" in states["states"]
    gj = json.loads((out / "states.geojson").read_text())
    assert {f["properties"]["name"] for f in gj["features"]} == {"StateA", "StateB"}
    results = json.loads((out / "results.json").read_text())
    assert {"primary", "test_2024", "bands", "validation"} <= set(results)
