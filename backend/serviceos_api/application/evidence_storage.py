"""Storage boundary for private case image bytes.

Only opaque server-generated keys cross this boundary. Business records retain
the metadata and key, while adapters own the bytes.
"""

from typing import Protocol


class EvidenceStorageFailure(OSError):
    """The configured private object store could not complete an operation."""


class EvidenceStorage(Protocol):
    def put(self, key: str, payload: bytes) -> None: ...

    def read(self, key: str, max_bytes: int) -> bytes: ...

    def delete(self, key: str) -> None: ...
