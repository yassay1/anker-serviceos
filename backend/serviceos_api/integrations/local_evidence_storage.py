"""Private local image storage for development and isolated tests.

Production needs a separately configured object-store adapter; it must not
silently fall back to a process-local directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from serviceos_api.application.evidence_storage import EvidenceStorage, EvidenceStorageFailure, validate_evidence_key
from serviceos_api.settings import Settings


class LocalEvidenceStorage:
    def __init__(self, root: Path):
        if not root.is_absolute():
            raise EvidenceStorageFailure("Evidence storage directory must be absolute.")
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        validate_evidence_key(key)
        parts = key.split("/")
        parent = (self.root / parts[0]).resolve()
        if self.root not in parent.parents:
            raise EvidenceStorageFailure("Evidence object key escapes the private store.")
        path = parent / parts[1]
        if path.is_symlink():
            raise EvidenceStorageFailure("Evidence object key points to a link.")
        return path

    def put(self, key: str, payload: bytes) -> None:
        path = self._path(key)
        temp_path: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise EvidenceStorageFailure("Evidence object already exists.")
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".pending-", delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError as error:
            raise EvidenceStorageFailure("Could not save evidence bytes.") from error
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def read(self, key: str, max_bytes: int) -> bytes:
        path = self._path(key)
        try:
            with path.open("rb") as handle:
                payload = handle.read(max_bytes + 1)
        except OSError as error:
            raise EvidenceStorageFailure("Could not read evidence bytes.") from error
        if len(payload) > max_bytes:
            raise EvidenceStorageFailure("Evidence object exceeds its recorded size.")
        return payload

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise EvidenceStorageFailure("Could not remove evidence bytes.") from error


def evidence_storage_from_settings(settings: Settings) -> EvidenceStorage:
    if settings.evidence_storage_backend == "s3":
        from serviceos_api.integrations.s3_evidence_storage import S3EvidenceStorage
        return S3EvidenceStorage(settings)
    if settings.environment not in ("development", "test"):
        raise EvidenceStorageFailure("A production object storage adapter is not configured.")
    root = Path(settings.evidence_storage_dir) if settings.evidence_storage_dir else (
        Path(__file__).resolve().parents[2] / ".data" / "evidence"
    )
    return LocalEvidenceStorage(root)
