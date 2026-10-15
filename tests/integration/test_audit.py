"""audit_source on a small archive: cross-file dedup, zero-detection days, compact dtypes."""

import importlib.util
from pathlib import Path

from terrasentinel.config import REPO_ROOT
from terrasentinel.ingestion.archive import RawArchive

spec = importlib.util.spec_from_file_location("audit", REPO_ROOT / "pipelines" / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
FIX = Path(__file__).parents[1] / "fixtures" / "viirs_sample.csv"
BBOX = {"west": 68, "south": 6, "east": 98, "north": 38}


def test_audit_source(tmp_path):
    arch = RawArchive(tmp_path)
    body = FIX.read_bytes()
    # Same data retrieved twice under overlapping requests (different bytes: extra trailing newline).
    arch.store("firms", "S", body, {"start_date": "2024-03-14", "day_range": 2})
    arch.store("firms", "S", body + b"\n", {"start_date": "2024-03-15", "day_range": 3})
    inside, lines = audit.audit_source(arch, "S", arch.records(), BBOX)
    text = "\n".join(lines)
    assert len(inside) == 3                                        # duplicates across files removed
    assert "cross-file duplicates removed: 3" in text
    assert "zero detections in the bbox: 3" in text                # 03-14, 03-16, 03-17 requested but empty
    assert "2024-03-16..2024-03-17 (2 d)" in text
    assert str(inside["satellite"].dtype) == "category" and str(inside["latitude"].dtype) == "float64"


def test_header_only_file_keeps_numeric_types(tmp_path):
    arch = RawArchive(tmp_path)
    body = FIX.read_bytes()
    header = body.split(b"\n", 1)[0] + b"\n"
    arch.store("firms", "S", header, {"start_date": "2024-03-10", "day_range": 1})   # outage day
    arch.store("firms", "S", body, {"start_date": "2024-03-15", "day_range": 1})
    inside, _ = audit.audit_source(arch, "S", arch.records(), BBOX)
    for c in ("bright_ti4", "bright_ti5", "scan", "track", "frp"):
        assert str(inside[c].dtype) == "float32", c
