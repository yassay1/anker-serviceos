"""Storage boundary for private case image bytes.

Only opaque server-generated keys cross this boundary. Business records retain
the metadata and key, while adapters own the bytes.
"""

from typing import Protocol
from uuid import UUID


class EvidenceStorageFailure(OSError):
    """The configured private object store could not complete an operation."""


def validate_evidence_key(key: str) -> None:
    parts = key.split("/")
    try:
        valid = len(parts) == 2 and all(str(UUID(part)) == part for part in parts)
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise EvidenceStorageFailure("Invalid evidence object key.")


class EvidenceStorage(Protocol):
    def put(self, key: str, payload: bytes) -> None: ...

    def read(self, key: str, max_bytes: int) -> bytes: ...

    def delete(self, key: str) -> None: ...
