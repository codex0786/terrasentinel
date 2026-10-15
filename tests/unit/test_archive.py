import os

import pytest

from terrasentinel.ingestion.archive import ArchiveIntegrityError, RawArchive


def test_store_is_idempotent_and_logs_every_retrieval(tmp_path):
    arch = RawArchive(tmp_path)
    r1 = arch.store("firms", "VIIRS_SNPP_SP", b"latitude,longitude\n1,2\n", {"q": 1})
    r2 = arch.store("firms", "VIIRS_SNPP_SP", b"latitude,longitude\n1,2\n", {"q": 1})
    assert r1.newly_written and not r2.newly_written
    assert r1.path == r2.path
    assert len(arch.records()) == 2
    assert arch.read(r1) == b"latitude,longitude\n1,2\n"


def test_different_content_never_overwrites(tmp_path):
    arch = RawArchive(tmp_path)
    r1 = arch.store("firms", "X", b"a", {})
    r2 = arch.store("firms", "X", b"b", {})
    assert r1.path != r2.path
    assert arch.read(r1) == b"a"


def test_payload_is_read_only(tmp_path):
    arch = RawArchive(tmp_path)
    r = arch.store("firms", "X", b"a", {})
    assert not os.access(tmp_path / r.path, os.W_OK)


def test_tampering_is_detected(tmp_path):
    arch = RawArchive(tmp_path)
    r = arch.store("firms", "X", b"original", {})
    p = tmp_path / r.path
    p.chmod(0o644)
    p.write_bytes(b"tampered")
    with pytest.raises(ArchiveIntegrityError):
        arch.read(r)
    with pytest.raises(ArchiveIntegrityError):
        arch.store("firms", "X", b"original", {})


def test_records_ignore_in_progress_append(tmp_path):
    arch = RawArchive(tmp_path)
    arch.store("firms", "X", b"a", {})
    with arch.manifest_path.open("a") as f:
        f.write('{"provider": "firms", "prod')          # concurrent writer, mid-line
    assert len(arch.records()) == 1
