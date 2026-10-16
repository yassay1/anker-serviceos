from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import UIActionRequest
from serviceos_api.application.diagnostic_contracts import DiagnosticResult
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import ConversationService
from serviceos_api.persistence.models import (
    AgentRun, DiagnosticAnswer, DiagnosticTask, Message, MessageJob, OutboxEvent, SpecialistRun,
)
from test_skills import active_skill_run


def waiting_task(session):
    tenant, customer, conversation, message, _, parent = active_skill_run(session)
    task_id = uuid4()
    task = DiagnosticTask(
        id=task_id,
        tenant_id=tenant.id, conversation_id=conversation.id, source_message_id=message.id,
        parent_agent_run_id=parent.id, case_id=message.related_case_id,
        idempotency_key="c" * 64, status="WAITING_CUSTOMER", version=3,
        input_payload={"task_id": str(task_id), "conversation_id": str(conversation.id), "goal": "核对供电问题"},
        result_payload={"certainty": "HYPOTHESIS"},
        question_payload={"prompt": "充电器指示灯是否亮起？", "options": ["亮起", "没有亮起"]},
        question_revision=1, expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(task)
    session.flush()
    specialist = SpecialistRun(
        tenant_id=tenant.id, diagnostic_task_id=task.id, parent_agent_run_id=parent.id,
        checkpoint_thread_id=f"diagnostic:{task.id}:initial", attempt=1, status="COMPLETED",
        lease_token=parent.lease_token, completed_at=datetime.now(timezone.utc),
    )
    session.add(specialist)
    session.flush()
    principal = Principal(tenant.id, customer.id, "CUSTOMER", "客户")
    service = ConversationService(session, principal)
    document = service.publish_ui_projection(conversation.id)
    return tenant, customer, conversation, message, parent, task, document, service


def answer_request(document, conversation, task, *, answer="亮起", task_version=None, revision=1, client_id=None):
    return UIActionRequest(
        client_action_id=client_id or uuid4(), ui_id=document.ui_id, revision=document.revision,
        action_id="submit-diagnostic-answer",
        input={"task_version": task_version if task_version is not None else task.version,
               "question_revision": revision, "answer": answer},
        expected_conversation_version=conversation.version,
    )


def test_diagnostic_question_ui_action_persists_one_answer_message_and_worker_job(db_session):
    tenant, customer, conversation, _, _, task, document, service = waiting_task(db_session)
    component = next(item for item in document.components if item.data_source.kind == "DIAGNOSTIC_TASK_VIEW")
    assert component.data_source.resource_version == task.version
    assert component.data_source.question_revision == task.question_revision
    assert component.type == "ChoiceGroup" and len(component.options) == 2
    request = answer_request(document, conversation, task, answer="亮起")

    accepted = service.invoke_ui_action(conversation.id, request)
    assert accepted.status == "ACCEPTED" and accepted.diagnostic_task_id == task.id and not accepted.replayed
    replay = service.invoke_ui_action(conversation.id, request)
    assert replay.replayed and replay.diagnostic_task_id == task.id
    answers = db_session.scalars(select(DiagnosticAnswer).where(
        DiagnosticAnswer.tenant_id == tenant.id, DiagnosticAnswer.diagnostic_task_id == task.id,
    )).all()
    assert len(answers) == 1 and answers[0].question_revision == 1 and answers[0].answer == "亮起"
    saved_message = db_session.get(Message, answers[0].source_message_id)
    assert saved_message.author_kind == "CUSTOMER" and saved_message.visibility == "PUBLIC"
    assert saved_message.client_message_id == request.client_action_id
    assert db_session.scalar(select(MessageJob).where(MessageJob.message_id == saved_message.id)) is not None
    assert task.status == "RUNNING" and task.version == 4
    events = db_session.scalars(select(OutboxEvent).where(
        OutboxEvent.conversation_id == conversation.id, OutboxEvent.type == "message.created",
    )).all()
    assert any(event.data.get("message_id") == str(saved_message.id) for event in events)


@pytest.mark.parametrize("change,expected", [
    ("stale_version", 409), ("wrong_option", 422), ("expired", 409), ("policy", 409),
])
def test_diagnostic_answer_refuses_stale_invalid_expired_or_restricted_submission(db_session, change, expected):
    _, _, conversation, _, _, task, document, service = waiting_task(db_session)
    request = answer_request(document, conversation, task,
                             answer="任意回答" if change == "wrong_option" else "亮起",
                             task_version=task.version - 1 if change == "stale_version" else None)
    if change == "expired":
        task.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if change == "policy":
        conversation.collaboration_mode, conversation.reply_policy = "CO_SERVICE", "AI_REVIEW_REQUIRED"
    with pytest.raises(ServiceError) as exc:
        service.invoke_ui_action(conversation.id, request)
    assert exc.value.status == expected
    assert not db_session.scalars(select(DiagnosticAnswer).where(
        DiagnosticAnswer.diagnostic_task_id == task.id,
    )).all()


def test_answer_resume_keeps_diagnostic_task_and_uses_persisted_answer(database_engine):
    from sqlalchemy.orm import Session
    from test_worker_runtime import seed_message

    with Session(database_engine) as session:
        tenant, customer, conversation, original_message, parent, task, document, service = waiting_task(session)
        accepted = service.invoke_ui_action(conversation.id, answer_request(document, conversation, task))
        answer = session.scalar(select(DiagnosticAnswer).where(
            DiagnosticAnswer.diagnostic_task_id == task.id,
        ))
        answer_message = session.get(Message, answer.source_message_id)
        job = session.scalar(select(MessageJob).where(MessageJob.message_id == answer_message.id))
        job.status = "RUNNING"
        job.attempt_count = 1
        job.lease_token = uuid4()
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        new_parent = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                              message_id=answer_message.id, thread_id=str(uuid4()), lease_token=job.lease_token,
                              provider="test", model="test")
        session.add(new_parent)
        session.flush()
        from serviceos_api.application.agent_services import AgentContextBuilder, AgentToolService

        context = AgentContextBuilder(session, tenant.id).build(conversation.id, answer_message.id, run_id=new_parent.id)
        assert context["diagnostic_resume"] == {"task_id": str(task.id), "answer_id": str(answer.id)}
        resumed_task, specialist, task_input, persisted_answer, cached = AgentToolService(
            session, tenant.id, conversation.id, new_parent.id, job.lease_token,
        ).resume_diagnostic(task.id, answer.id)
        assert cached is None and resumed_task.id == task.id and task_input.task_id == task.id
        assert persisted_answer.answer == "亮起" and specialist.parent_agent_run_id == new_parent.id
        assert specialist.attempt == 2 and specialist.checkpoint_thread_id != "diagnostic:initial"
        original_run_id, thread_id = specialist.id, specialist.checkpoint_thread_id
        retry_token = uuid4()
        job.lease_token = retry_token
        new_parent.lease_token = retry_token
        session.flush()
        _, recovered, _, _, recovered_cached = AgentToolService(
            session, tenant.id, conversation.id, new_parent.id, retry_token,
        ).resume_diagnostic(task.id, answer.id)
        assert recovered.id == original_run_id and recovered.checkpoint_thread_id == thread_id
        assert recovered_cached is None and recovered.lease_token == retry_token
        final_result = DiagnosticResult(
            task_id=task.id, assessment="供电连接仍需观察",
            next_step={"kind": "NO_ACTION", "summary": "按服务助手说明继续确认"}, staff_summary="待核验。",
        )
        AgentToolService(session, tenant.id, conversation.id, new_parent.id, retry_token).complete_diagnostic(
            task.id, recovered.id, final_result, {}, task_input,
        )
        _, _, _, _, cached = AgentToolService(
            session, tenant.id, conversation.id, new_parent.id, retry_token,
        ).resume_diagnostic(task.id, answer.id)
        assert cached is not None and cached.assessment == final_result.assessment


def test_diagnostic_answer_action_replay_cannot_be_reused_with_changed_payload(db_session):
    _, _, conversation, _, _, task, document, service = waiting_task(db_session)
    request = answer_request(document, conversation, task, client_id=uuid4())
    service.invoke_ui_action(conversation.id, request)
    changed = request.model_copy(update={"input": {**request.input, "answer": "没有亮起"}})
    with pytest.raises(ServiceError) as exc:
        service.invoke_ui_action(conversation.id, changed)
    assert exc.value.status == 409


def test_diagnostic_answer_is_customer_only_and_scoped_to_conversation_owner(db_session):
    tenant, _, conversation, _, _, task, document, service = waiting_task(db_session)
    request = answer_request(document, conversation, task)
    service.actor = Principal(tenant.id, uuid4(), "STAFF", "客服", "SUPPORT")
    with pytest.raises(ServiceError) as staff_error:
        service.invoke_ui_action(conversation.id, request)
    assert staff_error.value.status == 403
    service.actor = Principal(tenant.id, uuid4(), "CUSTOMER", "其他客户")
    with pytest.raises(ServiceError) as other_customer_error:
        service.invoke_ui_action(conversation.id, request)
    assert other_customer_error.value.status in (403, 404)
