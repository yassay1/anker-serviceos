from io import BytesIO
from uuid import uuid4

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from serviceos_api.application.evidence_storage import EvidenceStorageFailure
from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings
from serviceos_api.integrations.s3_evidence_storage import S3EvidenceStorage
from serviceos_api.settings import Settings


def client():
    return boto3.client("s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")


def settings():
    return Settings(evidence_storage_backend="s3", s3_bucket="serviceos-test-evidence", s3_region="us-east-1")


def test_s3_private_write_bounded_read_delete():
    sdk = client()
    storage = S3EvidenceStorage(settings(), client=sdk)
    key = f"{uuid4()}/{uuid4()}"
    args = {"Bucket": settings().s3_bucket, "Key": f"evidence/{key}"}
    with Stubber(sdk) as stub:
        stub.add_response("put_object", {}, {**args, "Body": b"image", "IfNoneMatch": "*", "ServerSideEncryption": "AES256", "ContentType": "application/octet-stream"})
        stub.add_response("get_object", {"Body": StreamingBody(BytesIO(b"image"), 5), "ContentLength": 5}, args)
        stub.add_response("delete_object", {}, args)
        storage.put(key, b"image")
        assert storage.read(key, 5) == b"image"
        storage.delete(key)
        stub.assert_no_pending_responses()


def test_s3_rejects_keys_and_oversize_without_leaking_error():
    sdk = client()
    storage = S3EvidenceStorage(settings(), client=sdk)
    with pytest.raises(EvidenceStorageFailure):
        storage.read("../private", 10)
    key = f"{uuid4()}/{uuid4()}"
    args = {"Bucket": settings().s3_bucket, "Key": f"evidence/{key}"}
    with Stubber(sdk) as stub:
        stub.add_response("get_object", {"Body": StreamingBody(BytesIO(b"too large"), 9), "ContentLength": 9}, args)
        with pytest.raises(EvidenceStorageFailure):
            storage.read(key, 5)
        stub.add_client_error("get_object", "AccessDenied", "secret external error", expected_params=args)
        with pytest.raises(EvidenceStorageFailure) as caught:
            storage.read(key, 20)
        assert "secret" not in str(caught.value)


def test_production_storage_never_falls_back_to_local():
    with pytest.raises(EvidenceStorageFailure):
        evidence_storage_from_settings(Settings())
    with pytest.raises(EvidenceStorageFailure):
        S3EvidenceStorage(Settings(evidence_storage_backend="s3"), client=client())
