"""Immutable raw-response archive.

Every response body is stored once, named by its SHA-256, with a metadata sidecar.
Re-running a retrieval that returns identical bytes is a no-op for the payload but is
still logged in the manifest, so the retrieval history is complete. Existing files are
never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ArchiveIntegrityError(RuntimeError):
    """An archived file no longer matches its recorded checksum."""


@dataclass(frozen=True)
class ArchiveRecord:
    provider: str
    product: str
    sha256: str
    path: str
    size_bytes: int
    retrieved_at_utc: str
    request: dict[str, Any]
    newly_written: bool


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class RawArchive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.jsonl"

    def _payload_path(self, provider: str, product: str, digest: str, suffix: str) -> Path:
        return self.root / provider / product / digest[:2] / f"{digest}{suffix}"

    def store(
        self,
        provider: str,
        product: str,
        content: bytes,
        request: dict[str, Any],
        suffix: str = ".csv",
        retrieved_at: datetime | None = None,
    ) -> ArchiveRecord:
        retrieved_at = retrieved_at or datetime.now(UTC)
        digest = sha256_bytes(content)
        path = self._payload_path(provider, product, digest, suffix)
        newly_written = False

        if path.exists():
            # Same name implies same digest; verify the stored bytes were not tampered with.
            if sha256_bytes(path.read_bytes()) != digest:
                raise ArchiveIntegrityError(f"Checksum mismatch for existing file {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(content)
            os.replace(tmp, path)
            path.chmod(0o444)
            newly_written = True

        record = ArchiveRecord(
            provider=provider,
            product=product,
            sha256=digest,
            path=str(path.relative_to(self.root)),
            size_bytes=len(content),
            retrieved_at_utc=retrieved_at.astimezone(UTC).isoformat(),
            request=request,
            newly_written=newly_written,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("a") as f:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def records(self) -> list[ArchiveRecord]:
        if not self.manifest_path.exists():
            return []
        text = self.manifest_path.read_text()
        if not text.endswith("\n"):
            # Another process is mid-append; its unterminated last line is not yet a record.
            text = text[: text.rfind("\n") + 1]
        return [ArchiveRecord(**json.loads(line)) for line in text.splitlines() if line.strip()]

    def read(self, record: ArchiveRecord, verify: bool = True) -> bytes:
        content = (self.root / record.path).read_bytes()
        if verify and sha256_bytes(content) != record.sha256:
            raise ArchiveIntegrityError(f"Checksum mismatch for {record.path}")
        return content
