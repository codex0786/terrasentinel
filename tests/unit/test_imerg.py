import numpy as np

from terrasentinel.ingestion.imerg import constraint, window

INDIA = {"west": 68, "south": 6, "east": 98, "north": 38}


def test_window_matches_project_grid():
    x0, x1, y0, y1 = window(INDIA)
    # IMERG cell centres: lon = -179.95 + 0.1 i, lat = -89.95 + 0.1 j
    assert np.isclose(-179.95 + 0.1 * x0, 68.05) and np.isclose(-179.95 + 0.1 * x1, 97.95)
    assert np.isclose(-89.95 + 0.1 * y0, 6.05) and np.isclose(-89.95 + 0.1 * y1, 37.95)
    assert (x1 - x0 + 1, y1 - y0 + 1) == (300, 320)


def test_constraint_requests_only_needed_variables():
    ce = constraint(INDIA)
    assert ce.startswith("/precipitation[0][2480:2779][960:1279];/precipitation_cnt")
    assert "randomError" not in ce


class _Resp:
    def __init__(self, code, content=b""):
        self.status_code, self.content = code, content


class _Session:
    def __init__(self, codes):
        self.codes = list(codes)

    def get(self, *a, **k):
        return _Resp(self.codes.pop(0))


def test_expired_login_is_renewed_once(tmp_path, monkeypatch):
    from terrasentinel.ingestion import imerg
    from terrasentinel.ingestion.archive import RawArchive

    monkeypatch.setattr(imerg, "check_subset", lambda c, b: None)
    fresh = _Session([200])
    c = imerg.ImergClient(RawArchive(tmp_path), _Session([401]), "C1", INDIA, session_factory=lambda: fresh)
    rec = c.fetch_one("GPM_3IMERGDF.07:3B-DAY.MS.MRG.3IMERG.20240101-S000000-E235959.V07B.nc4")
    assert rec.newly_written and c._renewals == 1


def test_persistent_401_raises(tmp_path):
    import pytest

    from terrasentinel.ingestion import imerg
    from terrasentinel.ingestion.archive import RawArchive

    c = imerg.ImergClient(RawArchive(tmp_path), _Session([401]), "C1", INDIA,
                          session_factory=lambda: _Session([401]))
    with pytest.raises(PermissionError, match="expired"):
        c.fetch_one("GPM_3IMERGDF.07:3B-DAY.MS.MRG.3IMERG.20240101-S000000-E235959.V07B.nc4")
