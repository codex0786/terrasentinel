import pandas as pd
import pytest

from terrasentinel.validation.firms_schema import (
    SchemaError,
    modis_confidence_class,
    normalize_firms,
    read_firms_csv,
)


def test_fixture_rows_reconcile(viirs_csv_bytes):
    df, rep = normalize_firms(read_firms_csv(viirs_csv_bytes), "VIIRS_NOAA20_NRT")
    assert rep.rows_in == 7
    assert rep.duplicates_removed == 1
    assert rep.dropped == {
        "invalid_coordinates": 1,
        "unparseable_time": 1,
        "invalid_confidence_or_instrument": 1,
    }
    assert rep.rows_out == len(df) == 3
    assert rep.reconciles()


def test_acq_time_is_zero_padded_and_utc(viirs_csv_bytes):
    df, _ = normalize_firms(read_firms_csv(viirs_csv_bytes), "VIIRS_NOAA20_NRT")
    first = df.iloc[0]
    assert first["acq_datetime_utc"] == pd.Timestamp("2024-03-15 08:12", tz="UTC")
    assert str(df["acq_datetime_utc"].dt.tz) == "UTC"


def test_viirs_confidence_mapping(viirs_csv_bytes):
    df, _ = normalize_firms(read_firms_csv(viirs_csv_bytes), "VIIRS_NOAA20_NRT")
    assert sorted(df["confidence_class"]) == ["high", "low", "nominal"]


def test_missing_required_column_raises(viirs_csv_bytes):
    raw = read_firms_csv(viirs_csv_bytes).drop(columns=["acq_time"])
    with pytest.raises(SchemaError, match="acq_time"):
        normalize_firms(raw, "VIIRS_NOAA20_NRT")


def test_unexpected_columns_are_reported_not_dropped_silently(viirs_csv_bytes):
    raw = read_firms_csv(viirs_csv_bytes).assign(new_field=1)
    _, rep = normalize_firms(raw, "VIIRS_NOAA20_NRT")
    assert rep.unexpected_columns == ["new_field"]


def test_modis_confidence_thresholds():
    pct = pd.Series([0, 29, 30, 79, 80, 100])
    assert list(modis_confidence_class(pct)) == ["low", "low", "nominal", "nominal", "high", "high"]


def test_modis_out_of_range_confidence_dropped():
    raw = pd.DataFrame({
        "latitude": [20.0, 20.1], "longitude": [80.0, 80.1],
        "acq_date": ["2024-03-15"] * 2, "acq_time": ["0500", "0500"],
        "satellite": ["Terra"] * 2, "instrument": ["MODIS"] * 2,
        "confidence": ["85", "150"], "version": ["6.1"] * 2, "daynight": ["D"] * 2,
    })
    df, rep = normalize_firms(raw, "MODIS_SP")
    assert len(df) == 1 and df.iloc[0]["confidence_class"] == "high"
    assert rep.dropped == {"invalid_confidence_or_instrument": 1}


def test_key_collisions_are_order_independent(viirs_csv_bytes):
    # Real case (VIIRS_SNPP_SP 2024-05-09): same key, different brightness/FRP, order varied between requests.
    raw = read_firms_csv(viirs_csv_bytes).iloc[[2]]
    twin = raw.assign(frp=99.0, bright_ti4=350.0)
    a, rep_a = normalize_firms(pd.concat([raw, twin]), "S")
    b, rep_b = normalize_firms(pd.concat([twin, raw]), "S")
    assert len(a) == 2 and rep_a.duplicates_removed == 0 and rep_a.key_collisions == 2
    pd.testing.assert_frame_equal(a, b)


def test_output_independent_of_input_row_order(viirs_csv_bytes):
    raw = read_firms_csv(viirs_csv_bytes)
    a, _ = normalize_firms(raw, "S")
    b, _ = normalize_firms(raw.iloc[::-1], "S")
    pd.testing.assert_frame_equal(a, b)


def test_header_only_csv_has_numeric_types(viirs_csv_bytes):
    header = viirs_csv_bytes.split(b"\n", 1)[0] + b"\n"
    df = read_firms_csv(header)
    assert len(df) == 0 and df["bright_ti4"].dtype == float and df["latitude"].dtype == float


def test_text_in_numeric_column_raises(viirs_csv_bytes):
    with pytest.raises(ValueError):
        read_firms_csv(viirs_csv_bytes.replace(b"330.1,", b"abc,", 1))
