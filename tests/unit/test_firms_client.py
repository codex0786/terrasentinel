from datetime import date

import pytest

from terrasentinel.ingestion.firms import BBox, area_url, iter_date_chunks
from terrasentinel.ingestion.http import RateLimiter, redact


def test_date_chunks_cover_range_exactly():
    chunks = list(iter_date_chunks(date(2024, 3, 1), date(2024, 3, 12)))
    assert chunks == [(date(2024, 3, 1), 5), (date(2024, 3, 6), 5), (date(2024, 3, 11), 2)]


def test_date_chunks_reject_reversed_range():
    with pytest.raises(ValueError):
        list(iter_date_chunks(date(2024, 3, 2), date(2024, 3, 1)))


def test_area_url_format():
    url = area_url("KEY", "VIIRS_SNPP_SP", BBox(68, 6, 98, 38), 5, date(2024, 3, 1))
    assert url == ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/KEY/VIIRS_SNPP_SP/"
                   "68,6,98,38/5/2024-03-01")


@pytest.mark.parametrize("kwargs", [{"source": "BOGUS"}, {"day_range": 6}, {"day_range": 0}])
def test_area_url_validation(kwargs):
    args = {"source": "VIIRS_SNPP_SP", "day_range": 1} | kwargs
    with pytest.raises(ValueError):
        area_url("KEY", args["source"], BBox(68, 6, 98, 38), args["day_range"], date(2024, 3, 1))


def test_invalid_bbox():
    with pytest.raises(ValueError):
        BBox(98, 6, 68, 38)


def test_redact():
    assert redact("url/abc123/x", ["abc123"]) == "url/***/x"


def test_rate_limiter_waits():
    t = [0.0]
    slept = []
    rl = RateLimiter(1.0, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    rl.wait()
    t[0] += 0.25
    rl.wait()
    assert slept == [pytest.approx(0.75)]
