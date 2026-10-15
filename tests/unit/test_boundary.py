import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from terrasentinel.geospatial.boundary import (
    assign_regions,
    assign_regions_by_cell,
    cell_regions,
    clip_detections,
    load_boundary,
)
from terrasentinel.geospatial.grid import Grid
from tests.geo_helpers import two_states


def test_assign_regions(tmp_path):
    b = two_states(tmp_path)
    r = assign_regions([15, 15, 15, 25], [75, 85, 80, 75], b)
    assert r[0] == "StateA" and r[1] == "StateB"
    assert r[2] in {"StateA", "StateB"}          # shared border: exactly one region
    assert pd.isna(r[3])                          # outside
    assert len(r) == 4


def test_clip_counts_reconcile(tmp_path):
    b = two_states(tmp_path)
    det = pd.DataFrame({"latitude": [15, 15, 25, 5], "longitude": [75, 85, 75, 75]})
    out, rep = clip_detections(det, b)
    assert rep.rows_in == 4 and rep.rows_inside == 2 and rep.rows_outside == 2
    assert rep.by_region == {"StateA": 1, "StateB": 1}
    assert list(out["region"]) == ["StateA", "StateB"]


def test_cell_regions_by_centre(tmp_path):
    b = two_states(tmp_path)
    g = Grid(0.1, 68.0, 6.0)
    ids = pd.Series(g.cell_id([15.05, 15.05, 25.0], [75.05, 85.05, 75.0]))
    m = cell_regions(g, ids, b).set_index("cell_id")["cell_region"]
    assert m[ids[0]] == "StateA" and m[ids[1]] == "StateB" and pd.isna(m[ids[2]])


def test_invalid_geometry_repaired(tmp_path):
    bowtie = Polygon([(70, 10), (80, 20), (80, 10), (70, 20)])
    path = tmp_path / "b.geojson"
    gpd.GeoDataFrame({"n": ["X"]}, geometry=[bowtie], crs="EPSG:4326").to_file(path)
    b = load_boundary(path, "n")
    assert b.geometry.is_valid.all()


def test_reprojects_to_wgs84(tmp_path):
    gdf = gpd.GeoDataFrame({"n": ["A"]}, geometry=[box(70, 10, 80, 20)], crs="EPSG:4326").to_crs("EPSG:3857")
    path = tmp_path / "m.geojson"
    gdf.to_file(path)
    b = load_boundary(path, "n")
    assert assign_regions([15], [75], b)[0] == "A"
    assert np.allclose(b.total_bounds, [70, 10, 80, 20])


def test_bad_name_field_and_duplicates(tmp_path):
    path = tmp_path / "d.geojson"
    gpd.GeoDataFrame({"n": ["A", "A"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326").to_file(path)
    with pytest.raises(KeyError):
        load_boundary(path, "missing")
    with pytest.raises(ValueError):
        load_boundary(path, "n")


def test_cell_path_matches_point_path(tmp_path):
    # Irregular boundary so many cells are border cells; points include edges, corners and outside.
    star = Polygon([(70, 10), (75, 18.37), (80, 10.05), (78.2, 15), (85, 19.9), (71.3, 19.6)])
    path = tmp_path / "s.geojson"
    gpd.GeoDataFrame({"n": ["S", "T"]}, geometry=[star, box(85, 10, 90, 20)], crs="EPSG:4326").to_file(path)
    b = load_boundary(path, "n")
    rng = np.random.default_rng(0)
    lat = np.r_[rng.uniform(9, 21, 20000), 15.0, 10.0, 15.0]
    lon = np.r_[rng.uniform(69, 91, 20000), 85.0, 70.0, 80.0]
    g = Grid(0.1, 68.0, 6.0)
    fast = assign_regions_by_cell(lat, lon, b, g)
    slow = assign_regions(lat, lon, b)
    pd.testing.assert_series_equal(fast.fillna("OUT"), slow.astype(object).fillna("OUT"), check_names=False)
