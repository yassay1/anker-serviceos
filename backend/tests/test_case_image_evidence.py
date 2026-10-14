"""Controlled image evidence: authorization, idempotency, inspection and recovery."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import UploadEvidence
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import EvidenceService
from serviceos_api.application.evidence_storage import EvidenceStorageFailure
from serviceos_api.application.image_safety import PROPOSAL_MAX_IMAGE_BYTES
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings
from serviceos_api.persistence.models import CaseImageEvidence, EvidenceInspectionJob, OutboxEvent
from serviceos_api.settings import Settings
from serviceos_api.worker.inspection import EvidenceInspectionWorker
from serviceos_api.worker.runtime import OutboxDispatcher, run_worker_forever
from test_business_api import conversation, login
from test_image_safety import jpeg_image, png_image, webp_image


def defer_other_jobs(engine, evidence_id):
    later = datetime.now(timezone.utc) + timedelta(days=1)
    with Session(engine) as session:
        session.execute(update(EvidenceInspectionJob).where(
            EvidenceInspectionJob.evidence_id != evidence_id,
            EvidenceInspectionJob.status.in_(("QUEUED", "RUNNING")),
        ).values(available_at=later, lease_expires_at=later))
        session.commit()


@pytest.fixture
def app(database_engine, tmp_path):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
        evidence_storage_dir=str(tmp_path / "evidence"),
    ))


def inspection_worker(app, database_engine, **overrides):
    return EvidenceInspectionWorker(database_engine, replace(app.state.settings, **overrides))


def case_for(client, text="端口没有反应"):
    created = client.post("/api/v1/cases", json={"problem_text": text})
    assert created.status_code == 201, created.text
    return created.json()


def upload(client, case, payload, content_type="image/png", visibility="PUBLIC", version=None, key=None):
    return client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        data={
            "client_evidence_id": str(key or uuid4()),
            "expected_case_version": str(version if version is not None else case["version"]),
            "visibility": visibility,
        },
        files={"file": ("evidence.bin", payload, content_type)},
    )


def test_message_worker_still_refuses_without_provider():
    with pytest.raises(RuntimeError, match="LLM provider is not configured"):
        run_worker_forever(Settings(environment="test"))


def test_customer_upload_is_pending_then_clean_and_replay_is_stable(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    conv = conversation(customer)
    case = case_for(customer)
    assert customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "conversation_id": conv["id"], "expected_version": case["version"],
    }).status_code == 200
    case = customer.get(f"/api/v1/cases/{case['id']}").json()
    key = uuid4()
    image = png_image()
    first = upload(customer, case, image, key=key)
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["client_evidence_id"] == str(key)
    assert body["inspection_status"] == "PENDING"
    assert body["verification"] == "UNVERIFIED"
    assert body["source_kind"] == "CUSTOMER"
    assert body["visibility"] == "PUBLIC"
    assert "content" not in body and "rejection_code" not in body
    assert customer.get(f"/api/v1/cases/{case['id']}/evidence/{body['id']}/content").status_code == 404
    replay = upload(customer, case, image, key=key, version=1)
    assert replay.status_code == 202, replay.text
    assert replay.json()["id"] == body["id"]
    conflict = upload(customer, case, jpeg_image(), content_type="image/jpeg", key=key, version=case["version"])
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(CaseImageEvidence).where(
            CaseImageEvidence.id == body["id"])) == 1
        assert session.scalar(select(func.count()).select_from(EvidenceInspectionJob).where(
            EvidenceInspectionJob.evidence_id == body["id"])) == 1
    defer_other_jobs(database_engine, UUID(body["id"]))
    worker = inspection_worker(app, database_engine, worker_max_attempts=3)
    assert worker.run_once() is True
    assert worker.run_once() is False
    listed = customer.get(f"/api/v1/cases/{case['id']}/evidence").json()["items"]
    assert listed[0]["client_evidence_id"] == str(key)
    assert listed[0]["inspection_status"] == "CLEAN"
    content = customer.get(f"/api/v1/cases/{case['id']}/evidence/{body['id']}/content")
    assert content.status_code == 200, content.text
    assert content.headers["content-type"].startswith("image/png")
    assert "no-store" in content.headers["cache-control"]
    assert content.content == image
    for _ in range(8):
        if OutboxDispatcher(database_engine).dispatch_batch() == 0:
            break
    events = customer.get(f"/api/v1/conversations/{conv['id']}/event-history").json()["items"]
    assert [item["type"] for item in events][-2:] == ["evidence.received", "evidence.inspected"]
    assert all(item["visibility"] == "PUBLIC" for item in events)
    with Session(database_engine) as session:
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == body["id"]))
        job.status = "QUEUED"
        job.lease_token = None
        job.lease_expires_at = None
        session.commit()
        before = session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.type == "evidence.inspected"))
    assert worker.run_once() is True
    with Session(database_engine) as session:
        evidence = session.get(CaseImageEvidence, UUID(body["id"]))
        assert evidence.inspection_status == "CLEAN"
        assert evidence.storage_key is not None
        assert worker.storage.read(evidence.storage_key, evidence.byte_size) == image
        after = session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.type == "evidence.inspected"))
        assert after == before
    assert staff.get(f"/api/v1/cases/{case['id']}").json()["version"] == case["version"] + 1


def test_visibility_tenant_and_validation_failures(app):
    owner = login(app)
    other = login(app, "customer-b")
    outside = login(app, "other-tenant")
    staff = login(app, "staff")
    anonymous = login(app)
    anonymous.cookies.clear()
    case = case_for(owner)
    assert anonymous.get(f"/api/v1/cases/{case['id']}/evidence").status_code == 401
    assert upload(anonymous, case, png_image()).status_code == 401
    for client in (other, outside):
        assert client.get(f"/api/v1/cases/{case['id']}/evidence").status_code == 404
        assert upload(client, case, png_image()).status_code == 404
    assert upload(owner, case, png_image(), visibility="INTERNAL").status_code == 403
    internal = upload(staff, case, png_image(), visibility="INTERNAL")
    assert internal.status_code == 202, internal.text
    assert internal.json()["visibility"] == "INTERNAL"
    assert owner.get(f"/api/v1/cases/{case['id']}/evidence").json()["items"] == []
    assert len(staff.get(f"/api/v1/cases/{case['id']}/evidence").json()["items"]) == 1
    public = upload(owner, owner.get(f"/api/v1/cases/{case['id']}").json(), webp_image(), content_type="image/webp")
    assert public.status_code == 202, public.text
    stale = upload(owner, case, png_image(), version=1)
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_VERSION"
    assert upload(owner, owner.get(f"/api/v1/cases/{case['id']}").json(), b"").status_code == 422
    assert upload(owner, owner.get(f"/api/v1/cases/{case['id']}").json(), b"GIF89ahello", content_type="image/gif").status_code == 415
    assert upload(owner, owner.get(f"/api/v1/cases/{case['id']}").json(), jpeg_image(), content_type="image/png").status_code == 415
    huge = b"\xff\xd8\xff" + b"\x00" * PROPOSAL_MAX_IMAGE_BYTES
    assert upload(owner, owner.get(f"/api/v1/cases/{case['id']}").json(), huge, content_type="image/jpeg").status_code == 413
    hidden = owner.get(f"/api/v1/cases/{case['id']}/evidence/{internal.json()['id']}/content")
    assert hidden.status_code == 404


def test_unsafe_image_is_rejected_and_not_served(app, database_engine):
    customer = login(app)
    case = case_for(customer)
    accepted = upload(customer, case, png_image() + b"<script>alert(1)</script>")
    assert accepted.status_code == 202, accepted.text
    evidence_id = accepted.json()["id"]
    defer_other_jobs(database_engine, UUID(evidence_id))
    worker = inspection_worker(app, database_engine)
    assert worker.run_once() is True
    listed = customer.get(f"/api/v1/cases/{case['id']}/evidence").json()["items"][0]
    assert listed["inspection_status"] == "REJECTED"
    assert "trailing_data" not in accepted.text
    assert customer.get(f"/api/v1/cases/{case['id']}/evidence/{evidence_id}/content").status_code == 404
    with Session(database_engine) as session:
        stored = session.get(CaseImageEvidence, UUID(evidence_id))
        assert stored.storage_key is None
        assert stored.rejection_code == "trailing_data"
    assert not list(Path(app.state.settings.evidence_storage_dir).rglob("*/*"))


def test_inspection_failure_retries_once_then_can_recover(app, database_engine, monkeypatch):
    customer = login(app)
    case = case_for(customer)
    accepted = upload(customer, case, png_image())
    evidence_id = accepted.json()["id"]
    defer_other_jobs(database_engine, UUID(evidence_id))

    def unavailable(media_type, payload):
        raise RuntimeError("scanner_unavailable")

    monkeypatch.setattr("serviceos_api.application.evidence.inspect_image", unavailable)
    worker = inspection_worker(app, database_engine, worker_max_attempts=2)
    assert worker.run_once() is True
    with Session(database_engine) as session:
        stored = session.get(CaseImageEvidence, UUID(evidence_id))
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == stored.id))
        assert stored.inspection_status == "PENDING"
        assert job.status == "QUEUED"
        assert job.last_error_code == "evidence_inspection_failed"
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    monkeypatch.setattr("serviceos_api.application.evidence.inspect_image", lambda media_type, payload: None)
    assert worker.run_once() is True
    with Session(database_engine) as session:
        stored = session.get(CaseImageEvidence, UUID(evidence_id))
        assert stored.inspection_status == "CLEAN"
        assert session.scalar(select(func.count()).select_from(CaseImageEvidence).where(
            CaseImageEvidence.case_id == UUID(case["id"]))) == 1


def test_expired_inspection_lease_recovers_without_a_second_file(app, database_engine):
    customer = login(app)
    case = case_for(customer)
    accepted = upload(customer, case, jpeg_image(), content_type="image/jpeg")
    evidence_id = UUID(accepted.json()["id"])
    defer_other_jobs(database_engine, evidence_id)
    with Session(database_engine) as session:
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == evidence_id))
        job.status = "RUNNING"
        job.attempt_count = 1
        job.lease_token = uuid4()
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        session.commit()
    worker = inspection_worker(app, database_engine)
    assert worker.run_once() is True
    with Session(database_engine) as session:
        stored = session.get(CaseImageEvidence, evidence_id)
        jobs = session.scalars(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == evidence_id)).all()
        assert stored.inspection_status == "CLEAN"
        assert len(jobs) == 1
        assert jobs[0].status == "COMPLETED"


def test_closed_case_rejects_new_evidence(app):
    customer = login(app)
    staff = login(app, "staff")
    case = case_for(customer)
    version = case["version"]
    for target in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        moved = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
            "target_status": target, "expected_version": version, "reason": "关闭历史案例",
        })
        assert moved.status_code == 200, moved.text
        version = moved.json()["version"]
    refused = upload(customer, {"id": case["id"], "version": version}, png_image(), version=version)
    assert refused.status_code == 409
    assert refused.json()["code"] == "CASE_CLOSED"


def test_same_case_version_allows_only_one_new_upload(app, database_engine):
    customer = login(app)
    case = case_for(customer)
    me = customer.get("/api/v1/auth/me").json()
    actor = Principal(tenant_id=UUID(me["tenant_id"]), actor_id=UUID(me["actor_id"]),
                      kind="CUSTOMER", display_name=me["display_name"])
    image = png_image()

    def send(key):
        with Session(database_engine) as session:
            service = EvidenceService(session, actor, evidence_storage_from_settings(app.state.settings))
            try:
                return service.upload(UUID(case["id"]), UploadEvidence(
                    client_evidence_id=key, expected_case_version=case["version"],
                ), image, "image/png").id
            except ServiceError as error:
                return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [uuid4(), uuid4()]))
    assert sorted(isinstance(item, int) for item in results) == [False, True]
    assert 409 in results
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(CaseImageEvidence).where(
            CaseImageEvidence.case_id == UUID(case["id"]))) == 1


def test_customer_cannot_page_with_hidden_cursor(app):
    customer = login(app)
    staff = login(app, "staff")
    case = case_for(customer)
    internal = upload(staff, case, png_image(), visibility="INTERNAL")
    assert internal.status_code == 202, internal.text
    cursor = internal.json()["id"]
    assert customer.get(f"/api/v1/cases/{case['id']}/evidence", params={"cursor": cursor}).status_code == 404
    listed = staff.get(f"/api/v1/cases/{case['id']}/evidence", params={"limit": 1})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == cursor


def test_database_failure_removes_private_object(app, database_engine, monkeypatch):
    customer = login(app)
    case = case_for(customer)
    me = customer.get("/api/v1/auth/me").json()
    actor = Principal(tenant_id=UUID(me["tenant_id"]), actor_id=UUID(me["actor_id"]),
                      kind="CUSTOMER", display_name=me["display_name"])
    with Session(database_engine) as session:
        service = EvidenceService(session, actor, evidence_storage_from_settings(app.state.settings))

        def fail_commit():
            raise RuntimeError("simulated database failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated database failure"):
            service.upload(UUID(case["id"]), UploadEvidence(
                client_evidence_id=uuid4(), expected_case_version=case["version"],
            ), png_image(), "image/png")
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(CaseImageEvidence).where(
            CaseImageEvidence.case_id == UUID(case["id"]))) == 0
    assert not list(Path(app.state.settings.evidence_storage_dir).rglob("*/*"))


@pytest.mark.parametrize("max_attempts", [1, 5])
@pytest.mark.parametrize("recovery", ["retry", "expired"])
def test_rejected_object_cleanup_retries_without_duplicate_event(app, database_engine, monkeypatch, max_attempts, recovery):
    customer = login(app)
    case = case_for(customer)
    accepted = upload(customer, case, png_image() + b"<script>")
    evidence_id = UUID(accepted.json()["id"])
    defer_other_jobs(database_engine, evidence_id)
    with Session(database_engine) as session:
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == evidence_id))
        job.max_attempts = max_attempts
        session.commit()
    worker = inspection_worker(app, database_engine, worker_max_attempts=1)
    original_delete = worker.storage.delete
    attempts = 0

    def fail_once(key):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise EvidenceStorageFailure("simulated cleanup failure")
        original_delete(key)

    monkeypatch.setattr(worker.storage, "delete", fail_once)
    assert worker.run_once() is True
    with Session(database_engine) as session:
        evidence = session.get(CaseImageEvidence, evidence_id)
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == evidence_id))
        assert evidence.inspection_status == "REJECTED"
        assert evidence.storage_key is not None
        assert job.status == "QUEUED" and job.attempt_count == 1
        inspected_events = session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "evidence.inspected", OutboxEvent.data["evidence_id"].astext == str(evidence_id),
        ))
        assert inspected_events == 1
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    if recovery == "expired":
        abandoned = worker.claim_one()
        assert abandoned is not None
        with Session(database_engine) as session:
            job = session.get(EvidenceInspectionJob, abandoned.item_id)
            assert job.attempt_count == 1
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
    assert worker.run_once() is True
    assert attempts == 2
    with Session(database_engine) as session:
        evidence = session.get(CaseImageEvidence, evidence_id)
        job = session.scalar(select(EvidenceInspectionJob).where(EvidenceInspectionJob.evidence_id == evidence_id))
        assert evidence.storage_key is None
        assert job.status == "COMPLETED" and job.attempt_count == 1
        assert job.max_attempts == max_attempts
        assert job.lease_token is None and job.lease_expires_at is None
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "evidence.inspected", OutboxEvent.data["evidence_id"].astext == str(evidence_id),
        )) == inspected_events
    assert not worker.run_once()
