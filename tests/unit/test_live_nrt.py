from datetime import UTC, date, datetime

from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.firms import BBox
from terrasentinel.live.nrt import label_final, latest_by_day, load_nrt, plan_fetch

BBOX = BBox(68, 6, 98, 38)


def test_plan_fetch_refreshes_recent_and_fills_gaps():
    have = {("S", "2026-10-10"): 1, ("S", "2026-10-13"): 1, ("S", "2026-10-14"): 1}
    plan = plan_fetch(have, ["S"], date(2026, 10, 10), date(2026, 10, 15), refresh_days=3, today=date(2026, 10, 15))
    assert [d.day for _, d in plan] == [11, 12, 13, 14, 15]   # 10th archived and old; 13-15 refreshed


def test_latest_version_wins(tmp_path, viirs_csv_bytes):
    arch = RawArchive(tmp_path)
    q = {"source": "VIIRS_SNPP_NRT", "bbox": BBOX.as_param(), "start_date": "2024-03-15", "day_range": 1}
    header = viirs_csv_bytes.split(b"\n", 1)[0] + b"\n"
    arch.store("firms", "VIIRS_SNPP_NRT", header, q, retrieved_at=datetime(2024, 3, 15, 6, tzinfo=UTC))
    arch.store("firms", "VIIRS_SNPP_NRT", viirs_csv_bytes, q, retrieved_at=datetime(2024, 3, 16, 6, tzinfo=UTC))
    latest = latest_by_day(arch, bbox=BBOX)
    assert len(latest) == 1 and arch.read(next(iter(latest.values()))) == viirs_csv_bytes
    det, inv = load_nrt(arch, date(2024, 3, 15), date(2024, 3, 15), bbox=BBOX)
    assert len(det) == 3 and inv["rows"].tolist() == [3]


def test_label_final_needs_day_end_plus_lag():
    d = date(2026, 10, 14)
    assert not label_final(d, datetime(2026, 10, 15, 3, tzinfo=UTC), lag_hours=3)
    assert label_final(d, datetime(2026, 10, 15, 6, tzinfo=UTC), lag_hours=3)
