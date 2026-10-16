"""Knowledge pipeline: upload, dedupe, permissions, chunking, worker states, reprocess."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.knowledge_pipeline import KnowledgePipelineService
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.integrations.local_evidence_storage import LocalEvidenceStorage
from serviceos_api.main import create_app
from serviceos_api.persistence.knowledge_models import (
    KnowledgeDocument, KnowledgeJob, KnowledgeSegment,
)
from serviceos_api.persistence.models import Customer, OutboxEvent, StaffUser, Tenant, TenantMembership
from serviceos_api.settings import Settings
from serviceos_api.worker.knowledge import KnowledgeWorker

LONG_SECTION = "\n\n".join(f"Paragraph {index} about heating battery safety checks."
                           for index in range(60))
MD_PAYLOAD = ("# Guide\n\nintro line\n\n## Section A\n\n" + LONG_SECTION + "\n").encode("utf-8")
CSV_PAYLOAD = "model,issue\nE25,robot does not charge\nE28,map lost\n".encode("utf-8")


@pytest.fixture
def pipeline_env(database_engine, tmp_path):
    def purge(session):
        for document in session.scalars(select(KnowledgeDocument)).all():
            session.delete(document)
        session.commit()

    with Session(database_engine, expire_on_commit=False) as session:
        purge(session)
        seed_local_accounts(session)
        tenant = session.scalar(select(Tenant).where(Tenant.slug == "local-demo-a"))
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        supervisor = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:supervisor"))
        customer = session.scalar(select(Customer).where(
            Customer.tenant_id == tenant.id, Customer.external_subject == "local:customer-a"))
        staff_role = session.scalar(select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id, TenantMembership.staff_user_id == staff.id)).role
        supervisor_role = session.scalar(select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.staff_user_id == supervisor.id)).role
        session.commit()
        env = SimpleNamespace(
            engine=database_engine,
            settings=Settings(environment="test", evidence_storage_dir=str(tmp_path)),
            storage=LocalEvidenceStorage(tmp_path),
            tenant_id=tenant.id, staff_id=staff.id, staff_role=staff_role,
            supervisor_id=supervisor.id, supervisor_role=supervisor_role, customer_id=customer.id,
        )
    assert env.staff_role == "SUPPORT" and env.supervisor_role == "SUPERVISOR"
    yield env
    with Session(database_engine) as session:
        purge(session)
        # Restore the session-scoped seed baseline for later modules.
        from serviceos_api.knowledge_ingest import ingest

        ingest(session)
        session.commit()


def staff_actor(env, role=None, staff_id=None):
    return Principal(env.tenant_id, staff_id or env.staff_id, "STAFF", "客服", role or env.staff_role)


def service_for(env, session, actor=None):
    return KnowledgePipelineService(session, actor or staff_actor(env), env.storage)


def run_worker(env, **settings_kwargs):
    settings = Settings(environment="test", evidence_storage_dir=str(env.settings.evidence_storage_dir),
                        **settings_kwargs)
    worker = KnowledgeWorker(env.engine, settings, worker_id="test-knowledge")
    return worker.run_once()


def test_upload_md_runs_pipeline_with_parent_child_segments_and_internal_event(pipeline_env):
    env = pipeline_env
    with Session(env.engine, expire_on_commit=False) as session:
        read, deduplicated = service_for(env, session).upload("guide.md", MD_PAYLOAD, None)
        session.commit()
        assert deduplicated is False and read.status == "UPLOADED"
        job = session.scalar(select(KnowledgeJob).where(KnowledgeJob.document_id == read.document_id))
        assert job.status == "QUEUED"
    assert run_worker(env) is True
    with Session(env.engine) as session:
        document = session.get(KnowledgeDocument, read.document_id)
        assert document.status == "STORED" and document.error_code is None
        segments = session.scalars(select(KnowledgeSegment).where(
            KnowledgeSegment.document_id == document.id).order_by(KnowledgeSegment.chunk_index)).all()
        parents = [segment for segment in segments if segment.skip_embedding]
        children = [segment for segment in segments if not segment.skip_embedding]
        assert parents and children
        assert all(child.parent_segment_id in {parent.id for parent in parents} for child in children
                   if child.title.startswith("Section A"))
        job = session.scalar(select(KnowledgeJob).where(KnowledgeJob.document_id == document.id))
        assert job.status == "COMPLETED"
        events = session.scalars(select(OutboxEvent).where(
            OutboxEvent.type == "knowledge.document_updated")).all()
        assert events and all(event.visibility == "INTERNAL" for event in events)


def test_upload_dedupe_customer_forbidden_type_and_size(pipeline_env):
    env = pipeline_env
    with Session(env.engine, expire_on_commit=False) as session:
        service = service_for(env, session)
        first, deduplicated = service.upload("rows.csv", CSV_PAYLOAD, None)
        session.commit()
        assert deduplicated is False
        second, deduplicated = service.upload("rows-copy.csv", CSV_PAYLOAD, None)
        assert deduplicated is True and second.document_id == first.document_id
        customer_service = KnowledgePipelineService(
            session, Principal(env.tenant_id, env.customer_id, "CUSTOMER", "客户"), env.storage)
        with pytest.raises(ServiceError) as caught:
            customer_service.upload("rows.csv", CSV_PAYLOAD, None)
        assert caught.value.status == 403
        with pytest.raises(ServiceError) as caught:
            service.upload("manual.pdf", b"%PDF-1.4 fake", None)
        assert caught.value.status == 415
        with pytest.raises(ServiceError) as caught:
            service.upload("big.md", b"# x\n\n" + b"a" * (10 * 1024 * 1024 + 1), None)
        assert caught.value.status == 413
        assert session.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.id == first.document_id)).status == "UPLOADED"


def test_csv_rows_become_kv_segments(pipeline_env):
    env = pipeline_env
    with Session(env.engine, expire_on_commit=False) as session:
        read, _ = service_for(env, session).upload("rows.csv", CSV_PAYLOAD, None)
        session.commit()
    assert run_worker(env) is True
    with Session(env.engine) as session:
        segments = session.scalars(select(KnowledgeSegment).where(
            KnowledgeSegment.document_id == read.document_id)).all()
        contents = {segment.content for segment in segments}
        assert "model: E25 | issue: robot does not charge" in contents
        assert all(segment.applicability == "STAFF_UPLOAD" for segment in segments)
        assert all(segment.curation["source_kind"] == "upload" for segment in segments)
        assert all(segment.curation["source_ref"] == "rows.csv" for segment in segments)


def test_failed_conversion_dead_letters_then_supervisor_reprocess(pipeline_env):
    env = pipeline_env
    with Session(env.engine, expire_on_commit=False) as session:
        read, _ = service_for(env, session).upload("bad.xlsx", b"not a zip archive", None)
        session.commit()
    assert run_worker(env, worker_max_attempts=1) is True
    with Session(env.engine, expire_on_commit=False) as session:
        document = session.get(KnowledgeDocument, read.document_id)
        assert document.status == "FAILED" and document.error_code == "knowledge_process_failed"
        job = session.scalar(select(KnowledgeJob).where(KnowledgeJob.document_id == document.id))
        assert job.status == "FAILED"
        support = service_for(env, session)
        with pytest.raises(ServiceError) as caught:
            support.reprocess(document.id)
        assert caught.value.status == 403
        supervisor_service = service_for(
            env, session, staff_actor(env, role=env.supervisor_role, staff_id=env.supervisor_id))
        refreshed = supervisor_service.reprocess(document.id)
        session.commit()
        assert refreshed.status == "UPLOADED"
        assert job.status == "QUEUED" and job.attempt_count == 0


def test_knowledge_routes_are_staff_only(pipeline_env, database_engine):
    env = pipeline_env
    app = create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
        evidence_storage_dir=str(env.settings.evidence_storage_dir),
    ))
    with Session(database_engine) as session:
        seed_local_accounts(session)
        session.commit()
    staff_client = TestClient(app)
    assert staff_client.post("/api/v1/local-auth/login", json={
        "username": "staff", "password": "test-only-password"}).status_code == 200
    upload = staff_client.post("/api/v1/knowledge/documents",
                               files={"file": ("rows.csv", CSV_PAYLOAD, "text/csv")})
    assert upload.status_code == 201, upload.text
    assert upload.json()["deduplicated"] is False
    listing = staff_client.get("/api/v1/knowledge/documents")
    assert listing.status_code == 200 and listing.json()["items"]
    customer_client = TestClient(app)
    assert customer_client.post("/api/v1/local-auth/login", json={
        "username": "customer-a", "password": "test-only-password"}).status_code == 200
    denied = customer_client.post("/api/v1/knowledge/documents",
                                  files={"file": ("rows.csv", CSV_PAYLOAD, "text/csv")})
    assert denied.status_code == 403
    assert customer_client.get("/api/v1/knowledge/documents").status_code == 403
