"""Parse and validate NASA POWER regional daily CSVs.

The fill value -999 means "source data missing"; it becomes NaN and is counted. Values outside
physically plausible ranges are an error (they would indicate a unit or parsing problem),
not something to clip silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
import pandas as pd

from terrasentinel.ingestion.power import HEADER_END

FILL_VALUE = -999.0
PLAUSIBLE = {  # inclusive bounds, in POWER's units
    "T2M_MAX": (-60.0, 60.0),     # deg C
    "RH2M": (0.0, 100.0),         # %
    "WS2M": (0.0, 60.0),          # m/s
    # mm/day. Upper bound just above the world 24 h record (~1,825 mm, Réunion 1966). 1,000 was too tight:
    # MERRA-2 has 1,038 mm at 20.5N 91.25E on 2017-07-22 inside a coherent storm (neighbours 744-856 mm).
    "PRECTOTCORR": (0.0, 2000.0),
}


class PowerSchemaError(ValueError):
    pass


@dataclass
class PowerReport:
    parameter: str
    rows: int = 0
    missing: int = 0


def parse_power_csv(content: bytes, parameter: str) -> tuple[pd.DataFrame, PowerReport]:
    """Return columns [lat, lon, date (UTC), value] and a report."""
    end = content.find(HEADER_END)
    if end < 0:
        raise PowerSchemaError("missing -END HEADER- marker")
    body = content[content.index(b"\n", end) + 1:]
    raw = pd.read_csv(BytesIO(body))
    expected = ["LAT", "LON", "YEAR", "DOY", parameter]
    if list(raw.columns) != expected:
        raise PowerSchemaError(f"{parameter}: expected columns {expected}, got {list(raw.columns)}")
    value = raw[parameter].astype(float).replace(FILL_VALUE, np.nan)
    lo, hi = PLAUSIBLE[parameter]
    bad = value.notna() & ~value.between(lo, hi)
    if bad.any():
        raise PowerSchemaError(f"{parameter}: {int(bad.sum())} value(s) outside [{lo}, {hi}], e.g. "
                               f"{value[bad].iloc[:3].tolist()}")
    date = (pd.to_datetime(raw["YEAR"].astype(str), format="%Y", utc=True)
            + pd.to_timedelta(raw["DOY"] - 1, unit="D"))
    out = pd.DataFrame({"lat": raw["LAT"].astype(float), "lon": raw["LON"].astype(float),
                        "date": date, "value": value.astype(np.float32)})
    return out, PowerReport(parameter, rows=len(out), missing=int(value.isna().sum()))
