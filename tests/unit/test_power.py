import numpy as np
import pandas as pd
import pytest

from terrasentinel.ingestion.power import Tile, tiles_for
from terrasentinel.validation.power_schema import PowerSchemaError, parse_power_csv

HEADER = b"""-BEGIN HEADER-
NASA/POWER Source Native Resolution Daily Data
The value for missing source data that cannot be computed or is outside of the sources availability range: -999
-END HEADER-
"""


def body(param, rows):
    return HEADER + f"LAT,LON,YEAR,DOY,{param}\n".encode() + "".join(f"{r}\n" for r in rows).encode()


def test_parse_and_fill_value():
    df, rep = parse_power_csv(body("T2M_MAX", ["20.0,70.0,2020,1,23.39", "20.0,70.625,2020,60,-999"]), "T2M_MAX")
    assert rep.rows == 2 and rep.missing == 1
    assert df["date"].iloc[1] == pd.Timestamp("2020-02-29", tz="UTC")   # leap year DOY 60
    assert np.isnan(df["value"].iloc[1])


def test_implausible_value_raises():
    with pytest.raises(PowerSchemaError, match="outside"):
        parse_power_csv(body("RH2M", ["20.0,70.0,2020,1,140"]), "RH2M")


def test_wrong_columns_raise():
    with pytest.raises(PowerSchemaError, match="expected columns"):
        parse_power_csv(body("RH2M", ["20.0,70.0,2020,1,40"]), "T2M_MAX")


def test_tiles_respect_limits_and_skip():
    tiles = tiles_for({"west": 68, "south": 6, "east": 98, "north": 38}, skip={"30,38,88,98"})
    assert len(tiles) == 11 and "30,38,88,98" not in {t.key() for t in tiles}
    with pytest.raises(ValueError):
        Tile(0, 11, 0, 5)
