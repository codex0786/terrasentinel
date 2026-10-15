from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def viirs_csv_bytes() -> bytes:
    return (FIXTURES / "viirs_sample.csv").read_bytes()


def make_detections(rows: list[tuple[str, str]], lag_hours: float = 0.0) -> pd.DataFrame:
    """rows: (cell_id, ISO acquisition time in UTC)."""
    df = pd.DataFrame(rows, columns=["cell_id", "acq"])
    acq = pd.to_datetime(df["acq"], utc=True)
    return pd.DataFrame({
        "cell_id": df["cell_id"],
        "acq_datetime_utc": acq,
        "available_at_utc": acq + pd.Timedelta(hours=lag_hours),
        "confidence_class": "nominal",
    })
