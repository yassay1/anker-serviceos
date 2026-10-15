import re

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from serviceos_api.application.evidence_storage import EvidenceStorageFailure, validate_evidence_key
from serviceos_api.settings import Settings


class S3EvidenceStorage:
    def __init__(self, settings: Settings, *, client=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", settings.s3_bucket) or not settings.s3_region:
            raise EvidenceStorageFailure("An explicit private S3 bucket and region are required.")
        prefix = settings.s3_prefix.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix):
            raise EvidenceStorageFailure("Invalid private evidence prefix.")
        self.bucket = settings.s3_bucket
        self.prefix = prefix
        try:
            self.client = client or boto3.client("s3", region_name=settings.s3_region,
                config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}))
        except BotoCoreError:
            raise EvidenceStorageFailure("S3 credentials or configuration are unavailable.") from None

    def _arguments(self, key: str) -> dict:
        validate_evidence_key(key)
        return {"Bucket": self.bucket, "Key": f"{self.prefix}/{key}"}

    def put(self, key: str, payload: bytes) -> None:
        arguments = self._arguments(key)
        try:
            self.client.put_object(**arguments, Body=payload, IfNoneMatch="*",
                                   ServerSideEncryption="AES256", ContentType="application/octet-stream")
        except (BotoCoreError, ClientError):
            raise EvidenceStorageFailure("Could not save private evidence bytes.") from None

    def read(self, key: str, max_bytes: int) -> bytes:
        arguments = self._arguments(key)
        if max_bytes < 0 or max_bytes > 10 * 1024 * 1024:
            raise EvidenceStorageFailure("Invalid evidence read limit.")
        body = None
        try:
            result = self.client.get_object(**arguments)
            body = result["Body"]
            if result.get("ContentLength", 0) > max_bytes:
                raise EvidenceStorageFailure("Evidence object exceeds its recorded size.")
            payload = body.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise EvidenceStorageFailure("Evidence object exceeds its recorded size.")
            return payload
        except (BotoCoreError, ClientError, OSError):
            raise EvidenceStorageFailure("Could not read private evidence bytes.") from None
        finally:
            if body is not None:
                body.close()

    def delete(self, key: str) -> None:
        arguments = self._arguments(key)
        try:
            self.client.delete_object(**arguments)
        except (BotoCoreError, ClientError):
            raise EvidenceStorageFailure("Could not remove private evidence bytes.") from None
