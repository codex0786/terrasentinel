import importlib.util

import pandas as pd
import pytest

from terrasentinel.config import REPO_ROOT
from terrasentinel.ingestion.archive import RawArchive
from tests.unit.test_power import body

spec = importlib.util.spec_from_file_location("build_weather", REPO_ROOT / "pipelines" / "build_weather.py")
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)
PARAMS = ["T2M_MAX", "RH2M", "WS2M", "PRECTOTCORR"]


def fill(arch, edge_value_b="30"):
    for p in PARAMS:
        # two tiles sharing the lat=14.0 edge row
        arch.store("nasa_power", p, body(p, ["6.0,70.0,2020,1,20", "14.0,70.0,2020,1,30"]),
                   {"tile": "6,14,68,78", "start_date": "2020-01-01"})
        arch.store("nasa_power", p, body(p, [f"14.0,70.0,2020,1,{edge_value_b}", "22.0,70.0,2020,1,40"]),
                   {"tile": "14,22,68,78", "start_date": "2020-01-01"})


def run(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bw, "REPO_ROOT", tmp_path)
    (tmp_path / "interim").mkdir(exist_ok=True)
    (tmp_path / "reports" / "audits").mkdir(parents=True, exist_ok=True)
    bw.main()
    return pd.read_parquet(tmp_path / "interim" / "power_daily.parquet")


def test_edges_deduplicated_and_wide(tmp_path, monkeypatch):
    fill(RawArchive(tmp_path / "raw"))
    out = run(tmp_path, monkeypatch)
    assert len(out) == 3 and list(out.columns) == ["lat", "lon", "date", *PARAMS]
    assert out.loc[out["lat"] == 14.0, "T2M_MAX"].item() == 30


def test_conflicting_edge_values_raise(tmp_path, monkeypatch):
    fill(RawArchive(tmp_path / "raw"), edge_value_b="31")
    with pytest.raises(ValueError, match="disagree"):
        run(tmp_path, monkeypatch)
