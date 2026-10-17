"""S1 loop guard: policy DMN resolution, publication guard, override, remedy taxonomy."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.agent_services import AgentToolService
from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import MockActionRequest
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.guard_service import GuardService
from serviceos_api.application.policies import resolve_policy_row
from serviceos_api.application.publication_guard import PublicationGuard, extract_entities
from serviceos_api.application.services import ConversationService
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.knowledge_ingest import ingest_policies
from serviceos_api.persistence.models import (
    AgentRun, CaseAction, Message, MessageJob, PublicationGuardDecision, ServiceCase, ServicePolicy,
)
from serviceos_api.settings import Settings
from test_worker_runtime import seed_message

TEST_SETTINGS = Settings(environment="test")


@pytest.fixture
def guard_env(database_engine):
    with Session(database_engine, expire_on_commit=False) as session:
        seed_local_accounts(session)
        ingest_policies(session)
        from serviceos_api.persistence.models import Tenant, StaffUser
        tenant = session.scalar(select(Tenant).where(Tenant.slug == "local-demo-a"))
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        supervisor = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:supervisor"))
        session.commit()
        yield SimpleNamespace(engine=database_engine, tenant_id=tenant.id,
                              staff_id=staff.id, supervisor_id=supervisor.id)


def active_run(session, tenant_id, conversation_id, message_id, job_id):
    token = uuid4()
    job = session.get(MessageJob, job_id)
    job.status = "RUNNING"
    job.lease_token = token
    job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    run = AgentRun(tenant_id=tenant_id, job_id=job_id, conversation_id=conversation_id,
                   message_id=message_id, thread_id=str(conversation_id), lease_token=token,
                   provider="test", model="test")
    session.add(run)
    session.flush()
    return run, token


def test_policy_seeds_load_and_dmn_priority_wins(guard_env):
    env = guard_env
    with Session(env.engine) as session:
        assert session.scalar(select(ServicePolicy).where(ServicePolicy.rule_id == "POL-AUTH-IN")) is not None
        row = resolve_policy_row(session, country="DE", channel="AUTHORIZED_DEALER",
                                 product_family="ROBOVAC", warranty_state="IN")
        assert row.rule_id == "POL-AUTH-IN"
        out = resolve_policy_row(session, country="DE", channel="UNAUTHORIZED",
                                 product_family="ROBOVAC", warranty_state="OUT")
        assert out.rule_id == "POL-UNAUTH-OUT"
        unknown = resolve_policy_row(session, country="DE", channel="DIRECT",
                                     product_family="ROBOVAC", warranty_state="UNKNOWN")
        assert unknown.rule_id == "POL-UNKNOWN"
        assert resolve_policy_row(session, country="DE", channel="NOPE",
                                  product_family="ROBOVAC", warranty_state="IN") is None
        # idempotent re-ingest
        before = session.scalar(select(ServicePolicy).where(ServicePolicy.rule_id == "POL-AUTH-IN")).version
        ingest_policies(session)
        after = session.scalar(select(ServicePolicy).where(ServicePolicy.rule_id == "POL-AUTH-IN")).version
        assert before == after


def test_resolve_policy_tool_envelope_carries_reason_code(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        service = AgentToolService(session, tenant.id, conversation.id, run.id, token,
                                   settings=TEST_SETTINGS)
        envelope = service.resolve_policy("德国", "AUTHORIZED_DEALER", "ROBOVAC", "IN")
        assert envelope.status == "OK"
        assert envelope.references[0]["rule_id"] == "POL-AUTH-IN"
        assert "REPAIR" in envelope.items[0]
        missing = service.resolve_policy("DE", "AUTHORIZED_DEALER", "ROBOVAC", "OUT")
        assert missing.references[0]["rule_id"] == "POL-AUTH-OUT"


def test_entity_extraction_kinds():
    entities = extract_entities("您的 T2352 在 2026-10-13 过保，耗电 20% ，错误码 7021")
    kinds = {entity.kind for entity in entities}
    assert {"model", "date", "number", "error_code"} <= kinds


def test_publication_guard_blocks_ungrounded_and_passes_grounded(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        run.result_payload = {"knowledge_references": [
            {"entry_key": "k1", "source_ref": "s", "source_sha256_16": "x", "path": "keyword"}],
            "tool_envelopes": []}
        session.flush()
        from serviceos_api.persistence.knowledge_models import (
            KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSegment,
        )
        document = KnowledgeDocument(source_kind="manual", title="t", filename="t.md",
                                     media_type="text/markdown", content_hash="b" * 64,
                                     status="STORED", current_version=1, split_type="ROW")
        session.add(document)
        session.flush()
        version = KnowledgeDocumentVersion(document_id=document.id, version=1,
                                           content_hash="b" * 64, status="STORED")
        session.add(version)
        session.flush()
        session.add(KnowledgeSegment(
            document_id=document.id, version_id=version.id, chunk_index=0, entry_key="k1",
            title="t", content="Omni E28 T2352 keeps losing the map", content_sha256="a" * 64,
            models=[], directories=[], source_status="S", consumer_visible="V",
            applicability="A", curation={}))
        session.flush()
        guard = PublicationGuard(session, tenant.id)
        blocked = guard.check("您的 T9999 需要寄修。", run, conversation.id, "你好")
        assert blocked.decision == "BLOCKED" and "UNGROUNDED_ENTITY" in blocked.reason_codes
        passed = guard.check("您的 T2352 可能丢图，请重建地图。", run, conversation.id, "你好")
        assert passed.decision == "PASSED"


def test_order_tool_reference_grounds_only_the_returned_order_row(guard_env):
    env = guard_env
    from serviceos_api.persistence.knowledge_models import (
        KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSegment,
    )

    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        document = KnowledgeDocument(source_kind="seed_corpus", title="reference orders",
                                     filename="orders.jsonl", media_type="application/json",
                                     content_hash="c" * 64, status="STORED", current_version=1,
                                     split_type="ROW")
        session.add(document)
        session.flush()
        version = KnowledgeDocumentVersion(document_id=document.id, version=1,
                                           content_hash="c" * 64, status="STORED")
        session.add(version)
        session.flush()
        session.add(KnowledgeSegment(
            document_id=document.id, version_id=version.id, chunk_index=0,
            entry_key="orders-test:r3", title="订单 Anker002",
            content="Anker002 T2080GA1 S1 Pro warranty ends 2027-09-13",
            content_sha256="d" * 64, models=["T2080GA1"], directories=[],
            source_status="S", consumer_visible="V", applicability="REFERENCE_ORDER",
            attrs={"order_no": "anker002", "sku": "T2080GA1",
                   "description": "eufy RoboVac S1 Pro", "warranty_end": "2027-09-13",
                   "status": "已发货", "carrier": "ANPOST"},
            curation={"source_ref": "orders-test:r3"},
        ))
        session.flush()

        tool_service = AgentToolService(session, tenant.id, conversation.id, run.id, token,
                                        settings=TEST_SETTINGS)
        result = tool_service.query_order_warranty("Anker002")
        session.refresh(run)
        order_audit = run.result_payload["tool_envelopes"][-1]
        assert result.status == "OK" and "2027-09-13" in result.to_prompt_text()
        assert "items" not in order_audit  # Keep raw tool results out of generic audit.

        guard = PublicationGuard(session, tenant.id)
        valid = guard.check(
            "Anker002 的质保到 2027-09-13，订单显示已发货，承运商为 ANPOST。",
            run, conversation.id, "请查一下 Anker002 的订单。",
        )
        assert valid.decision == "PASSED"

        wrong_date = guard.check(
            "Anker002 的质保到 2026-10-13。", run, conversation.id,
            "请查一下 Anker002 的订单。",
        )
        assert wrong_date.decision == "BLOCKED"
        assert "UNGROUNDED_ENTITY" in wrong_date.reason_codes

        # A reference from another tool cannot authorize an order row as evidence.
        run.result_payload = {"tool_envelopes": [{
            **order_audit, "tool": "lookup_manual",
        }]}
        unrelated = guard.check("质保到 2027-09-13。", run, conversation.id, "谢谢")
        assert unrelated.decision == "BLOCKED"

        # Nor can a forged/mismatched source or corpus revision authorize the row.
        wrong_source = {**order_audit, "references": [{
            **order_audit["references"][0], "source_ref": "orders-test:other",
        }]}
        run.result_payload = {"tool_envelopes": [wrong_source]}
        forged = guard.check("质保到 2027-09-13。", run, conversation.id, "谢谢")
        assert forged.decision == "BLOCKED"

        wrong_revision = {**order_audit, "references": [{
            **order_audit["references"][0], "source_sha256_16": "0" * 16,
        }]}
        run.result_payload = {"tool_envelopes": [wrong_revision]}
        stale = guard.check("质保到 2027-09-13。", run, conversation.id, "谢谢")
        assert stale.decision == "BLOCKED"


def test_publish_hook_blocks_then_supervisor_override_publishes(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        service = ConversationService(session, actor=None, settings=Settings(
            environment="test", publication_guard=True))
        published = service.publish_agent_response(tenant.id, conversation.id, run.id, token,
                                                     "请确认型号后再继续。")
        assert published.visibility == "PUBLIC"
        decision = session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.run_id == run.id))
        assert decision.decision == "PASSED"

        tenant2, _, conversation2, message2, job2, _ = seed_message(session)
        run2, token2 = active_run(session, tenant2.id, conversation2.id, message2.id, job2.id)
        blocked_message = service.publish_agent_response(
            tenant2.id, conversation2.id, run2.id, token2, "您的 E99 型号已过保，我们保证明天修好。")
        assert blocked_message.visibility == "INTERNAL"
        decision2 = session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.run_id == run2.id))
        assert decision2.decision == "BLOCKED" and "UNGROUNDED_ENTITY" in decision2.reason_codes
        assert decision2.proposal_id is not None

        support = GuardService(session, Principal(tenant2.id, env.staff_id, "STAFF", "客服", "SUPPORT"))
        with pytest.raises(ServiceError) as caught:
            support.override(decision2.id)
        assert caught.value.status == 403
        supervisor = GuardService(session, Principal(tenant2.id, env.supervisor_id, "STAFF", "主管", "SUPERVISOR"))
        refreshed = supervisor.override(decision2.id)
        assert refreshed.decision == "OVERRIDDEN" and refreshed.override_by == env.supervisor_id
        assert session.get(Message, blocked_message.id).visibility == "PUBLIC"
        stats = supervisor.stats()
        assert stats.passed >= 1 and stats.blocked == 0 and stats.overridden == 1


def test_guard_disabled_publishes_directly(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        service = ConversationService(session, actor=None, settings=Settings(
            environment="test", publication_guard=False))
        published = service.publish_agent_response(tenant.id, conversation.id, run.id, token,
                                                     "无据型号 T9999 也会直接发布。")
        assert published.visibility == "PUBLIC"
        assert session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.run_id == run.id)) is None


def test_live_guard_skips_semantic_coverage_even_when_provider_configured(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run, token = active_run(session, tenant.id, conversation.id, message.id, job.id)
        settings = Settings(environment="test", llm_model="m", llm_api_key="k",
                            llm_base_url="https://llm.invalid")
        assert settings.llm_configured
        guard = PublicationGuard(session, tenant.id)
        original_blocked_reply = (
            "明白，是 Anker 充电配件在使用中间歇性断电。为了给你对应的排查步骤，需要先确认具体型号"
            "（型号一般印在机身或插头侧面，形如 A1234 这样的编号）。\n\n"
            "另外先确认安全情况：如果配件有鼓包、变形、冒烟、焦味、漏液或明显发烫，请立即停止使用和充电，"
            "不要自行拆机，直接告诉我，我会优先按安全流程处理。\n\n"
            "方便的话请提供：1）型号编号；2）是给哪类设备充电时断电（手机/笔记本/耳机等）；"
            "3）大概多久断一次、是否伴随发热或异响。"
        )
        outcome = guard.check(
            original_blocked_reply,
            run, conversation.id, "设备使用时会间歇性断电。",
        )
        assert outcome.decision == "PASSED"
        assert outcome.reason_codes == []
        assert outcome.verifier == {"status": "not_run_live"}

        published = ConversationService(session, actor=None, settings=settings).publish_agent_response(
            tenant.id, conversation.id, run.id, token, original_blocked_reply,
        )
        assert published.visibility == "PUBLIC"
        decision = session.scalar(select(PublicationGuardDecision).where(
            PublicationGuardDecision.run_id == run.id))
        assert decision is not None and decision.decision == "PASSED"
        assert decision.verifier["status"] == "not_run_live"
        assert "promises" not in decision.verifier and "unaddressed" not in decision.verifier


def test_mock_action_requires_remedy_type(guard_env):
    env = guard_env
    with Session(env.engine, expire_on_commit=False) as session:
        from serviceos_api.application.actions import ServiceActionService
        tenant, customer, conversation, message, job, case = seed_message(session, with_case=True)
        service = ServiceActionService(session, Principal(tenant.id, env.staff_id, "STAFF", "客服", "SUPPORT"))
        with pytest.raises(Exception):
            MockActionRequest.model_validate({
                "client_action_id": str(uuid4()), "expected_case_version": case.version,
                "action_kind": "MOCK_SERVICE_REQUEST", "reason": "客户申请寄修"})
        command = MockActionRequest.model_validate({
            "client_action_id": str(uuid4()), "expected_case_version": case.version,
            "action_kind": "MOCK_SERVICE_REQUEST", "remedy_type": "REPAIR", "reason": "客户申请寄修"})
        read = service.request(case.id, command)
        assert read.remedy_type == "REPAIR"
        assert session.get(CaseAction, read.id).remedy_type == "REPAIR"
