import pandas as pd
import pytest

from terrasentinel.geospatial.grid import Grid, in_bbox

GRID = Grid(resolution_deg=0.1, origin_lon=68.0, origin_lat=6.0)


@pytest.mark.parametrize(
    "lat, lon, expected",
    [
        (6.0, 68.0, "r0_c0"),          # origin corner belongs to the first cell
        (6.05, 68.05, "r0_c0"),
        (6.1, 68.1, "r1_c1"),          # north/east edge belongs to the neighbour
        (6.3, 68.3, "r3_c3"),          # 0.3/0.1 floating error must not give r2
        (28.6139, 77.2090, "r226_c92"),  # New Delhi
        (19.0760, 72.8777, "r130_c48"),  # Mumbai
    ],
)
def test_known_coordinates(lat, lon, expected):
    assert GRID.cell_id([lat], [lon])[0] == expected


def test_cell_center_round_trip():
    lat, lon = GRID.cell_center(226, 92)
    assert GRID.cell_id([lat], [lon])[0] == "r226_c92"


def test_in_bbox():
    df = pd.DataFrame({"latitude": [20.0, 40.0, 5.0], "longitude": [80.0, 80.0, 80.0]})
    bbox = {"west": 68, "south": 6, "east": 98, "north": 38}
    assert list(in_bbox(df, bbox)) == [True, False, False]
