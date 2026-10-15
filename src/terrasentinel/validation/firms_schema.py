"""Schema validation and normalization for FIRMS detection CSVs.

Missing required columns raise. Row-level problems (invalid coordinates, unparseable
times, unknown confidence codes) are dropped and *counted*, never silently coerced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "latitude", "longitude", "acq_date", "acq_time", "satellite",
    "instrument", "confidence", "version", "daynight",
)
OPTIONAL_COLUMNS = ("frp", "bright_ti4", "bright_ti5", "brightness", "bright_t31",
                    "scan", "track", "type")
# Identity of a detection. NOT guaranteed unique: FIRMS can return two records with the same key but
# different brightness/FRP (e.g. overlapping scan pixels). Such rows are kept and counted as key
# collisions; only exact duplicate rows are removed. See validate test_key_collisions_are_order_independent.
DEDUP_KEY = ("source", "satellite", "latitude", "longitude", "acq_datetime_utc")
VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


class SchemaError(ValueError):
    pass


@dataclass
class ValidationReport:
    source: str
    rows_in: int = 0
    rows_out: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    duplicates_removed: int = 0
    key_collisions: int = 0
    unexpected_columns: list[str] = field(default_factory=list)

    def drop(self, reason: str, n: int) -> None:
        if n:
            self.dropped[reason] = self.dropped.get(reason, 0) + int(n)

    def reconciles(self) -> bool:
        return self.rows_in == self.rows_out + sum(self.dropped.values()) + self.duplicates_removed


def modis_confidence_class(pct: pd.Series) -> pd.Series:
    """FIRMS guidance for MODIS: <30 low, 30-79 nominal, >=80 high."""
    return pd.Series(
        np.select([pct < 30, pct < 80], ["low", "nominal"], default="high"), index=pct.index
    ).where(pct.notna())


def sort_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Order rows by the detection key, then by every remaining column, so output never depends on
    the order the server returned rows in."""
    lead = ["acq_datetime_utc", "latitude", "longitude", "source", "satellite"]  # time-ordered first
    rest = sorted(c for c in df.columns if c not in lead)
    return df.sort_values(lead + rest, kind="mergesort", na_position="last").reset_index(drop=True)


NUMERIC_COLUMNS = ("latitude", "longitude", "bright_ti4", "bright_ti5", "brightness", "bright_t31",
                   "scan", "track", "frp", "type")
STRING_COLUMNS = ("acq_date", "acq_time", "satellite", "instrument", "confidence", "version", "daynight")


def read_firms_csv(content: bytes) -> pd.DataFrame:
    """Read with explicit types so a header-only response (no detections) has the same column
    types as a populated one. Non-numeric text in a numeric column raises instead of coercing."""
    df = pd.read_csv(BytesIO(content), dtype={c: str for c in STRING_COLUMNS})
    for c in NUMERIC_COLUMNS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="raise").astype(float)
    return df


def normalize_firms(raw: pd.DataFrame, source: str) -> tuple[pd.DataFrame, ValidationReport]:
    report = ValidationReport(source=source, rows_in=len(raw))
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SchemaError(f"{source}: missing required columns {missing}")
    known = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    report.unexpected_columns = sorted(c for c in raw.columns if c not in known)

    df = raw.copy()
    df["source"] = source
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    bad_coord = (df["latitude"].isna() | df["longitude"].isna()
                 | ~df["latitude"].between(-90, 90) | ~df["longitude"].between(-180, 180))
    report.drop("invalid_coordinates", bad_coord.sum())
    df = df[~bad_coord]

    hhmm = df["acq_time"].astype(str).str.strip().str.zfill(4)
    ts = pd.to_datetime(df["acq_date"].astype(str) + " " + hhmm, format="%Y-%m-%d %H%M",
                        errors="coerce", utc=True)
    report.drop("unparseable_time", ts.isna().sum())
    df = df.assign(acq_datetime_utc=ts)[ts.notna()]

    instrument = df["instrument"].astype(str).str.upper()
    conf_raw = df["confidence"].astype(str).str.strip().str.lower()
    is_viirs = instrument.eq("VIIRS")
    is_modis = instrument.eq("MODIS")
    pct = pd.to_numeric(conf_raw.where(is_modis), errors="coerce")
    conf_class = pd.Series(pd.NA, index=df.index, dtype="object")
    conf_class[is_viirs] = conf_raw[is_viirs].map(VIIRS_CONFIDENCE)
    conf_class[is_modis] = modis_confidence_class(pct)[is_modis]
    bad_conf = conf_class.isna() | ~(is_viirs | is_modis) | (is_modis & ~pct.between(0, 100))
    report.drop("invalid_confidence_or_instrument", bad_conf.sum())
    df = df.assign(confidence_class=conf_class, confidence_pct=pct, instrument=instrument)
    df = df[~bad_conf]

    if "frp" in df.columns:
        df["frp"] = pd.to_numeric(df["frp"], errors="coerce")

    before = len(df)
    df = df.drop_duplicates(subset=[c for c in raw.columns] + ["source"])
    report.duplicates_removed = before - len(df)
    report.key_collisions = int(df.duplicated(subset=list(DEDUP_KEY), keep=False).sum())

    df = sort_canonical(df)
    report.rows_out = len(df)
    assert report.reconciles(), report
    return df, report
