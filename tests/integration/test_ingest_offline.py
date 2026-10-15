"""End-to-end ingestion against a fake HTTP session (no network)."""

from datetime import date

import pytest

from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.ingestion.firms import BBox, FirmsClient, FirmsResponseError
from terrasentinel.ingestion.http import FetchError
from terrasentinel.validation.firms_schema import normalize_firms, read_firms_csv


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self.content = body
        self.text = body.decode()


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        return self.responses.pop(0)


BBOX = BBox(68, 6, 98, 38)


def client(tmp_path, responses, **kw):
    return FirmsClient("SECRETKEY", RawArchive(tmp_path), session=FakeSession(responses),
                       min_interval_s=0, **kw)


def test_fetch_archive_normalize(tmp_path, viirs_csv_bytes):
    c = client(tmp_path, [FakeResponse(200, viirs_csv_bytes)])
    rec = c.fetch_chunk("VIIRS_NOAA20_NRT", BBOX, date(2024, 3, 15), 1)
    assert "SECRETKEY" not in str(rec)  # key never persisted
    assert "SECRETKEY" not in (tmp_path / "manifest.jsonl").read_text()
    df, rep = normalize_firms(read_firms_csv(c.archive.read(rec)), rec.product)
    assert rep.rows_out == 3


def test_repeated_ingestion_is_idempotent(tmp_path, viirs_csv_bytes):
    c = client(tmp_path, [FakeResponse(200, viirs_csv_bytes)] * 2)
    a = c.fetch_chunk("VIIRS_NOAA20_NRT", BBOX, date(2024, 3, 15), 1)
    b = c.fetch_chunk("VIIRS_NOAA20_NRT", BBOX, date(2024, 3, 15), 1)
    assert a.sha256 == b.sha256 and b.newly_written is False
    assert len(list((tmp_path / "firms").rglob("*.csv"))) == 1


def test_error_body_with_http_200_is_rejected(tmp_path):
    c = client(tmp_path, [FakeResponse(200, b"Invalid MAP_KEY.")])
    with pytest.raises(FirmsResponseError):
        c.fetch_chunk("VIIRS_SNPP_SP", BBOX, date(2024, 3, 15), 1)
    assert not (tmp_path / "manifest.jsonl").exists()


def test_retries_then_succeeds(tmp_path, viirs_csv_bytes, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = client(tmp_path, [FakeResponse(503, b"busy"), FakeResponse(200, viirs_csv_bytes)])
    rec = c.fetch_chunk("VIIRS_SNPP_SP", BBOX, date(2024, 3, 15), 1)
    assert rec.newly_written


def test_non_retryable_error_redacts_key(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = client(tmp_path, [FakeResponse(400, b"bad request")])
    with pytest.raises(FetchError) as exc:
        c.fetch_chunk("VIIRS_SNPP_SP", BBOX, date(2024, 3, 15), 1)
    assert "SECRETKEY" not in str(exc.value)
    assert len(c.session.urls) == 1


def test_request_budget_enforced(tmp_path):
    c = client(tmp_path, [])
    with pytest.raises(ValueError, match="budget"):
        c.fetch_range("VIIRS_SNPP_SP", BBOX, date(2024, 1, 1), date(2024, 12, 31), max_requests=10)


def test_skip_archived_resumes_without_refetching(tmp_path, viirs_csv_bytes):
    c = client(tmp_path, [FakeResponse(200, viirs_csv_bytes)] * 3)
    c.fetch_range("VIIRS_SNPP_SP", BBOX, date(2024, 3, 1), date(2024, 3, 10))       # 2 chunks
    recs = c.fetch_range("VIIRS_SNPP_SP", BBOX, date(2024, 3, 1), date(2024, 3, 15), skip_archived=True)
    assert [r.request["start_date"] for r in recs] == ["2024-03-11"]
    assert len(c.session.urls) == 3


def test_transaction_limit_waits_then_succeeds(tmp_path, viirs_csv_bytes, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    waits = []
    c = FirmsClient("SECRETKEY", RawArchive(tmp_path), min_interval_s=0, limit_wait_s=600, sleep=waits.append,
                    session=FakeSession([FakeResponse(400, b"Exceeding allowed transaction limit."),
                                         FakeResponse(200, viirs_csv_bytes)]))
    rec = c.fetch_chunk("VIIRS_SNPP_SP", BBOX, date(2024, 3, 15), 1)
    assert rec.newly_written and waits == [600]


def test_transaction_limit_gives_up_eventually(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    limit = FakeResponse(400, b"Exceeding allowed transaction limit.")
    c = FirmsClient("SECRETKEY", RawArchive(tmp_path), min_interval_s=0, limit_retries=2, sleep=lambda s: None,
                    session=FakeSession([limit] * 3))
    with pytest.raises(FetchError, match="transaction limit"):
        c.fetch_chunk("VIIRS_SNPP_SP", BBOX, date(2024, 3, 15), 1)
