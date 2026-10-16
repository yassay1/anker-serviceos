from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from serviceos_api.application.agent_services import AgentToolService
from serviceos_api.application.diagnostic_contracts import DiagnosticResult
from serviceos_api.application.auth import Principal
from serviceos_api.application.services import ConversationService
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.persistence.models import (
    AgentRun, CaseConversation, CaseEvidence, Conversation, Customer, DiagnosticTask, Message, MessageJob,
    OutboxEvent, ServiceCase, SpecialistRun, Tenant,
)
from serviceos_api.application.contracts import MessageRead


def seed_active_agent_run(session):
    seed_local_accounts(session)
    tenant = session.scalar(select(Tenant).where(Tenant.slug == "local-demo-a"))
    customer = session.scalar(select(Customer).where(
        Customer.tenant_id == tenant.id, Customer.external_subject == "local:customer-a",
    ))
    conversation = Conversation(tenant_id=tenant.id, customer_id=customer.id)
    session.add(conversation)
    session.flush()
    case = ServiceCase(tenant_id=tenant.id, customer_id=customer.id, problem_text="设备连接后没有充电")
    session.add(case)
    session.flush()
    session.add(CaseConversation(tenant_id=tenant.id, case_id=case.id, conversation_id=conversation.id))
    message = Message(
        tenant_id=tenant.id, conversation_id=conversation.id, author_kind="CUSTOMER",
        author_customer_id=customer.id, visibility="PUBLIC",
        content=[{"type": "text", "text": "接上后没有充电"}], client_message_id=uuid4(), request_hash="b" * 64,
        related_case_id=case.id,
    )
    session.add(message)
    session.flush()
    token = uuid4()
    job = MessageJob(
        tenant_id=tenant.id, message_id=message.id, conversation_id=conversation.id,
        status="RUNNING", attempt_count=1, lease_token=token,
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    session.add(job)
    session.flush()
    parent_run = AgentRun(
        tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id, message_id=message.id,
        thread_id=str(uuid4()), lease_token=token, status="RUNNING", provider="test", model="test-model",
    )
    session.add(parent_run)
    session.flush()
    return tenant, conversation, case, message, parent_run, token


def test_diagnostic_task_and_specialist_run_are_idempotent_and_lease_bound(db_session):
    tenant, conversation, case, message, parent_run, token = seed_active_agent_run(db_session)
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": [], "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)

    task, specialist_run, task_input, cached = service.start_diagnostic("确认无法充电原因", context, "接上后没有充电")
    replay_task, replay_run, replay_input, replay_cached = service.start_diagnostic(
        "确认无法充电原因", context, "接上后没有充电",
    )

    assert task.id == replay_task.id
    assert specialist_run.id == replay_run.id
    assert task_input.task_id == replay_input.task_id
    assert cached is None and replay_cached is None
    assert specialist_run.lease_token == token
    assert task.source_message_id == message.id and task.case_id == case.id
    assert len(db_session.scalars(select(DiagnosticTask).where(
        DiagnosticTask.tenant_id == tenant.id, DiagnosticTask.conversation_id == conversation.id,
    )).all()) == 1
    assert len(db_session.scalars(select(SpecialistRun).where(
        SpecialistRun.tenant_id == tenant.id, SpecialistRun.diagnostic_task_id == task.id,
    )).all()) == 1
    with pytest.raises(ValueError, match="diagnostic_already_delegated"):
        service.start_diagnostic("另一个诊断目标", context, "接上后没有充电")


def test_diagnostic_result_cannot_cite_unrelated_evidence(db_session):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": [], "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, specialist_run, task_input, _ = service.start_diagnostic("确认原因", context, "无法充电")
    result = DiagnosticResult(
        task_id=task.id, assessment="可能是线材问题", evidence_refs=[
            {"ref_id": str(uuid4()), "supports": "无授权来源"},
        ], next_step={"kind": "ASK_CUSTOMER", "summary": "确认线材", "question": {"prompt": "当前使用的线材是什么类型？"}}, staff_summary="待核验假设。",
    )

    with pytest.raises(ValueError, match="diagnostic_result_reference_not_authorized"):
        service.complete_diagnostic(task.id, specialist_run.id, result, {}, task_input)

    assert task.result_payload is None
    assert task.status == "RUNNING"


def test_completed_diagnostic_result_is_durable_and_reused(db_session):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    case_evidence = CaseEvidence(
        tenant_id=tenant.id, case_id=case.id, source="customer statement", claim_type="USER_STATEMENT",
        certainty="MEDIUM", validity="CANDIDATE", summary="客户报告插线后无反应",
    )
    db_session.add(case_evidence)
    db_session.flush()
    evidence_id = case_evidence.id
    evidence = [{"evidence_id": str(evidence_id), "summary": "客户报告插线后无反应"}]
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": evidence, "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, specialist_run, task_input, _ = service.start_diagnostic("分析无法充电", context, "无法充电")
    result = DiagnosticResult(
        task_id=task.id, assessment="可能是供电连接问题", evidence_refs=[
            {"ref_id": str(evidence_id), "supports": "客户报告插线后无反应"},
        ], unknowns=["尚未确认充电器状态"],
        next_step={"kind": "ASK_CUSTOMER", "summary": "确认充电器指示灯", "question": {"prompt": "充电器指示灯是否亮起？"}},
        staff_summary="这是一项尚未核验的假设。",
    )

    stored = service.complete_diagnostic(task.id, specialist_run.id, result, {"input_tokens": 12}, task_input)
    replay_task, replay_run, _, cached = service.start_diagnostic("分析无法充电", context, "无法充电")

    assert stored["certainty"] == "HYPOTHESIS"
    assert replay_task.id == task.id and replay_run.id == specialist_run.id
    assert cached is not None and cached.assessment == result.assessment
    assert task.status == "WAITING_CUSTOMER" and specialist_run.status == "COMPLETED"


def test_task_rejects_two_active_specialist_runs(db_session):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    context = {"linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
               "linked_devices": [], "case_evidence": [], "public_history": []}
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, _, _, _ = service.start_diagnostic("确认原因", context, "无法充电")
    db_session.add(SpecialistRun(
        tenant_id=tenant.id, diagnostic_task_id=task.id, parent_agent_run_id=parent_run.id,
        checkpoint_thread_id=f"diagnostic:{uuid4()}", attempt=2, status="RUNNING", lease_token=token,
    ))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_lost_parent_lease_cannot_complete_diagnostic(db_session):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    evidence_id = uuid4()
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": [{"evidence_id": str(evidence_id), "summary": "客户报告无反应"}],
        "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, specialist_run, task_input, _ = service.start_diagnostic("确认原因", context, "无法充电")
    db_session.execute(update(MessageJob).where(MessageJob.id == parent_run.job_id).values(lease_token=uuid4()))
    result = DiagnosticResult(
        task_id=task.id, assessment="可能是供电问题", evidence_refs=[
            {"ref_id": str(evidence_id), "supports": "客户报告无反应"},
        ], next_step={"kind": "ASK_CUSTOMER", "summary": "确认供电适配器", "question": {"prompt": "你当前使用的适配器规格是什么？"}}, staff_summary="待核验假设。",
    )

    with pytest.raises(ValueError, match="agent_run_lease_lost"):
        service.complete_diagnostic(task.id, specialist_run.id, result, {}, task_input)

    assert task.result_payload is None


def test_changed_case_version_blocks_stale_specialist_result(db_session):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": [], "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, specialist_run, task_input, _ = service.start_diagnostic("确认原因", context, "无法充电")
    case.version += 1
    db_session.flush()
    result = DiagnosticResult(
        task_id=task.id, assessment="可能是供电问题",
        next_step={"kind": "ASK_CUSTOMER", "summary": "确认充电器", "question": {"prompt": "充电器指示灯是否亮起？"}}, staff_summary="待核验假设。",
    )

    with pytest.raises(ValueError, match="diagnostic_context_stale"):
        service.complete_diagnostic(task.id, specialist_run.id, result, {}, task_input)

    assert task.result_payload is None


def test_diagnostic_task_allows_no_case_and_rejects_invalid_status(db_session):
    tenant, conversation, _, _, parent_run, token = seed_active_agent_run(db_session)
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    context = {"linked_cases": [], "linked_devices": [], "case_evidence": [], "public_history": []}
    task, _, _, _ = service.start_diagnostic("排查用户问题", context, "设备无法使用")

    assert task.case_id is None
    task.status = "NOT_A_DIAGNOSTIC_STATUS"
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_diagnostic_task_cannot_reference_another_tenants_conversation(db_session):
    from serviceos_api.persistence.models import Customer, Tenant

    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    context = {"linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
               "linked_devices": [], "case_evidence": [], "public_history": []}
    task, _, _, _ = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token).start_diagnostic(
        "排查用户问题", context, "设备无法使用",
    )
    other_tenant = Tenant(slug="diagnostic-other-tenant", name="Other tenant")
    db_session.add(other_tenant)
    db_session.flush()
    other_customer = Customer(tenant_id=other_tenant.id, display_name="Other", external_subject="other-customer")
    db_session.add(other_customer)
    db_session.flush()
    other_conversation = Conversation(tenant_id=other_tenant.id, customer_id=other_customer.id)
    db_session.add(other_conversation)
    db_session.flush()
    task.conversation_id = other_conversation.id

    with pytest.raises(IntegrityError):
        db_session.flush()


def _diagnostic_fixture(db_session, *, mode="AI_LEAD", policy="AI_AUTO"):
    tenant, conversation, case, _, parent_run, token = seed_active_agent_run(db_session)
    conversation.collaboration_mode = mode
    conversation.reply_policy = policy
    context = {
        "linked_cases": [{"id": str(case.id), "version": case.version, "problem": case.problem_text}],
        "linked_devices": [], "case_evidence": [], "public_history": [],
    }
    service = AgentToolService(db_session, tenant.id, conversation.id, parent_run.id, token)
    task, specialist, task_input, _ = service.start_diagnostic("分析当前故障", context, "接上后没有充电")
    result = DiagnosticResult(
        task_id=task.id,
        assessment="可能是电源连接不稳定",
        next_step={"kind": "EXPLAIN", "summary": "检查电源连接是否牢固"},
        staff_summary="仅供客服参考的内部摘要，不应出现在专家消息中。",
    )
    return tenant, conversation, parent_run, task, specialist, task_input, result, service


def test_completed_diagnostic_publishes_one_safe_specialist_message_and_outbox(db_session):
    tenant, conversation, parent, task, specialist, task_input, result, service = _diagnostic_fixture(db_session)

    service.complete_diagnostic(task.id, specialist.id, result, {}, task_input)
    message = db_session.scalar(select(Message).where(Message.specialist_run_id == specialist.id))
    events = db_session.scalars(select(OutboxEvent).where(
        OutboxEvent.conversation_id == conversation.id, OutboxEvent.type == "message.created",
    )).all()

    assert message is not None
    assert message.author_kind == "SPECIALIST" and message.visibility == "PUBLIC"
    assert MessageRead.model_validate(message).author_display_name == "诊断专家"
    assert message.client_message_id == specialist.id and message.request_hash
    assert message.author_customer_id is None and message.author_staff_id is None
    body = message.content[0]["text"]
    assert "初步假设（待核验）" in body and "下一步建议（待确认）" in body
    assert "仅供客服参考" not in body and "内部摘要" not in body
    assert sum(event.data.get("message_id") == str(message.id) for event in events) == 1
    assert any(event.data.get("message_id") == str(message.id) and event.visibility == "PUBLIC" for event in events)

    replay = ConversationService(db_session, actor=None).publish_specialist_result(
        tenant.id, conversation.id, parent.id, parent.lease_token, task.id, specialist.id,
    )
    assert replay.id == message.id
    assert len(db_session.scalars(select(Message).where(Message.specialist_run_id == specialist.id)).all()) == 1
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(Message(
                tenant_id=tenant.id, conversation_id=conversation.id, author_kind="SPECIALIST",
                specialist_run_id=specialist.id, visibility="PUBLIC", content=message.content,
                client_message_id=uuid4(), request_hash="f" * 64,
            ))
            db_session.flush()


def test_message_author_constraints_require_specialist_source_and_forbid_forged_sources(db_session):
    tenant, conversation, _, _, specialist, _, _, _ = _diagnostic_fixture(db_session)
    invalid_rows = [
        Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="SPECIALIST",
                visibility="PUBLIC", content=[{"type": "text", "text": "未授权专家消息"}]),
        Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="AGENT",
                specialist_run_id=specialist.id, visibility="INTERNAL",
                content=[{"type": "text", "text": "伪造专家来源"}]),
    ]
    for row in invalid_rows:
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.add(row)
                db_session.flush()


def test_specialist_publication_failure_rolls_back_result_and_result_event(db_session, monkeypatch):
    tenant, conversation, _, task, specialist, task_input, result, service = _diagnostic_fixture(db_session)

    def fail_publish(*args, **kwargs):
        raise RuntimeError("simulated_publication_failure")

    monkeypatch.setattr(ConversationService, "publish_specialist_result", fail_publish)
    with pytest.raises(RuntimeError, match="simulated_publication_failure"):
        service.complete_diagnostic(task.id, specialist.id, result, {}, task_input)
    db_session.rollback()

    saved_task = db_session.get(DiagnosticTask, task.id)
    saved_run = db_session.get(SpecialistRun, specialist.id)
    saved_messages = db_session.scalars(select(Message).where(Message.specialist_run_id == specialist.id)).all()
    events = db_session.scalars(select(OutboxEvent).where(
        OutboxEvent.tenant_id == tenant.id, OutboxEvent.conversation_id == conversation.id,
        OutboxEvent.type == "specialist.activity",
    )).all()
    assert saved_task.result_payload is None and saved_task.status == "RUNNING"
    assert saved_run.result_payload is None and saved_run.status == "RUNNING"
    assert saved_messages == []
    assert all(event.data.get("stage") != "RESULT_READY" for event in events)


@pytest.mark.parametrize(("mode", "policy", "expected_visibility"), [
    ("AI_LEAD", "AI_AUTO", "PUBLIC"),
    ("CO_SERVICE", "AI_REVIEW_REQUIRED", "INTERNAL"),
    ("HUMAN_LEAD", "HUMAN_ONLY", "INTERNAL"),
])
def test_diagnostic_result_message_uses_current_collaboration_visibility(
        db_session, mode, policy, expected_visibility):
    tenant, conversation, _, task, specialist, task_input, result, service = _diagnostic_fixture(
        db_session, mode=mode, policy=policy,
    )

    service.complete_diagnostic(task.id, specialist.id, result, {}, task_input)
    message = db_session.scalar(select(Message).where(Message.specialist_run_id == specialist.id))

    assert message is not None and message.visibility == expected_visibility
    customer = db_session.scalar(select(Customer).where(Customer.id == conversation.customer_id))
    customer_service = ConversationService(db_session, Principal(tenant.id, customer.id, "CUSTOMER", "客户"))
    customer_messages = customer_service.messages(conversation.id).items
    assert (message.id in {item.id for item in customer_messages}) is (expected_visibility == "PUBLIC")


@pytest.mark.parametrize(("kind", "next_step", "expected_task_status"), [
    ("question", {"kind": "ASK_CUSTOMER", "summary": "确认充电器", "question": {"prompt": "指示灯是否亮起？"}}, "WAITING_CUSTOMER"),
    ("safety", {"kind": "SAFETY_STOP", "summary": "停止使用并联系人工"}, "WAITING_STAFF"),
    ("human", {"kind": "HUMAN_REVIEW", "summary": "请客服核实"}, "WAITING_STAFF"),
])
def test_question_safety_and_human_review_do_not_publish_specialist_message(
        db_session, kind, next_step, expected_task_status):
    _, _, _, task, specialist, task_input, _, service = _diagnostic_fixture(db_session)
    result = DiagnosticResult(
        task_id=task.id, assessment="可能存在供电问题", next_step=next_step,
        staff_summary="内部摘要。",
    )

    service.complete_diagnostic(task.id, specialist.id, result, {}, task_input)

    assert task.status == expected_task_status
    assert db_session.scalar(select(Message.id).where(Message.specialist_run_id == specialist.id)) is None
