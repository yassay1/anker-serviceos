from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from serviceos_api.application.agent_services import AgentContextBuilder, MAX_AGENT_RUN_TOOL_EXECUTIONS
from serviceos_api.application.agent_services import AgentToolService
from serviceos_api.agents.result import AgentOutputInvalidError, AgentResult
from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import ProposalDecision
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import ConversationService
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.persistence.models import (
    AgentProposal, AgentRun, CaseConversation, CaseDevice, Conversation, ConversationEvent,
    Customer, DeviceFact, DevicePassport, Message, MessageJob, OutboxEvent, ServiceCase, StaffUser, Tenant,
)
from serviceos_api.settings import Settings
from serviceos_api.worker.runtime import MessageWorker, OutboxDispatcher


def seed_message(session, *, with_case=False):
    # This module shares the session-scoped disposable database with API acceptance tests.
    session.execute(update(MessageJob).where(
        MessageJob.status.in_(("QUEUED", "RUNNING")),
    ).values(status="CANCELLED", lease_owner=None, lease_token=None, lease_expires_at=None))
    # Earlier tests in this shared database leave publishable events (e.g. agent.progress) that no
    # dispatcher consumed. Retire them so a later test's claim_batch() sees only its own event.
    session.execute(update(OutboxEvent).where(
        OutboxEvent.published_at.is_(None), OutboxEvent.dead_lettered_at.is_(None),
    ).values(published_at=datetime.now(timezone.utc), lease_owner=None, lease_token=None,
             lease_expires_at=None))
    seed_local_accounts(session)
    tenant = session.scalar(select(Tenant).where(Tenant.slug == "local-demo-a"))
    customer = session.scalar(select(Customer).where(
        Customer.tenant_id == tenant.id, Customer.external_subject == "local:customer-a",
    ))
    conversation = Conversation(tenant_id=tenant.id, customer_id=customer.id)
    session.add(conversation)
    session.flush()
    case = None
    if with_case:
        case = ServiceCase(tenant_id=tenant.id, customer_id=customer.id, problem_text="设备没有开始充电")
        session.add(case)
        session.flush()
        session.add(CaseConversation(tenant_id=tenant.id, case_id=case.id, conversation_id=conversation.id))
    message = Message(
        tenant_id=tenant.id, conversation_id=conversation.id, author_kind="CUSTOMER",
        author_customer_id=customer.id, visibility="PUBLIC", content=[{"type": "text", "text": "接上后没有充电"}],
        client_message_id=uuid4(), request_hash="a" * 64,
        related_case_id=case.id if case else None,
    )
    session.add(message)
    session.flush()
    job = MessageJob(tenant_id=tenant.id, message_id=message.id, conversation_id=conversation.id)
    session.add(job)
    session.flush()
    return tenant, customer, conversation, message, job, case


def test_parent_agent_run_tool_budget_is_shared_and_persisted(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        token = uuid4()
        now = datetime.now(timezone.utc)
        job.status = "RUNNING"
        job.lease_owner = "budget-test"
        job.lease_token = token
        job.lease_expires_at = now + timedelta(minutes=5)
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(uuid4()), lease_token=token,
                       provider="test", model="test", status="RUNNING")
        session.add(run)
        session.flush()
        service = AgentToolService(session, tenant.id, conversation.id, run.id, token,
                                   Settings(environment="test"))

        for _ in range(MAX_AGENT_RUN_TOOL_EXECUTIONS):
            service._active_execution(reserve_tool_call=True)
        session.commit()
        assert run.result_payload["tool_execution_count"] == MAX_AGENT_RUN_TOOL_EXECUTIONS
        with pytest.raises(ValueError, match="agent_run_tool_limit_reached"):
            service._active_execution(reserve_tool_call=True)


def test_message_job_lease_is_fenced_and_serialized(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, _, job, _ = seed_message(session)
        session.commit()
        job_id = job.id
        tenant_id = tenant.id
        conversation_id = conversation.id

    settings = Settings(environment="test", worker_lease_seconds=30, worker_heartbeat_seconds=5)
    first_worker = MessageWorker(database_engine, settings, worker_id="worker-one")
    second_worker = MessageWorker(database_engine, settings, worker_id="worker-two")
    first = first_worker.claim_one()
    assert first is not None and first.item_id == job_id
    assert second_worker.claim_one() is None
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    recovered = second_worker.claim_one()
    assert recovered is not None and recovered.item_id == job_id and recovered.token != first.token
    assert first_worker.heartbeat(first) is False
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        assert job.tenant_id == tenant_id and job.conversation_id == conversation_id
        assert job.attempt_count == 2 and job.status == "RUNNING"
        assert job.lease_token == recovered.token


def test_workers_claim_different_conversations_without_overlapping_one_conversation(database_engine):
    with Session(database_engine) as session:
        tenant, customer, first_conversation, _, first_job, _ = seed_message(session)
        other = Conversation(tenant_id=tenant.id, customer_id=customer.id)
        session.add(other)
        session.flush()
        for conversation in (first_conversation, other):
            message = Message(tenant_id=tenant.id, conversation_id=conversation.id,
                              author_kind="CUSTOMER", author_customer_id=customer.id,
                              visibility="PUBLIC", content=[{"type": "text", "text": "并行队列检查"}],
                              client_message_id=uuid4(), request_hash="b" * 64)
            session.add(message)
            session.flush()
            session.add(MessageJob(tenant_id=tenant.id, message_id=message.id,
                                   conversation_id=conversation.id))
        session.commit()
        first_id, other_id = first_conversation.id, other.id
    settings = Settings(environment="test")
    first_worker = MessageWorker(database_engine, settings)
    second_worker = MessageWorker(database_engine, settings)
    first, second = first_worker.claim_one(), second_worker.claim_one()
    assert first is not None and second is not None
    with Session(database_engine) as session:
        claimed = {session.get(MessageJob, lease.item_id).conversation_id for lease in (first, second)}
        assert claimed == {first_id, other_id}
    assert MessageWorker(database_engine, settings).claim_one() is None


def test_next_turn_waits_for_earlier_turn_retry(database_engine):
    with Session(database_engine) as session:
        tenant, customer, conversation, _, job, _ = seed_message(session)
        now = datetime.now(timezone.utc)
        job.created_at, job.available_at = now - timedelta(seconds=10), now + timedelta(minutes=1)
        message = Message(tenant_id=tenant.id, conversation_id=conversation.id,
                          author_kind="CUSTOMER", author_customer_id=customer.id, visibility="PUBLIC",
                          content=[{"type": "text", "text": "上一轮还没回答"}],
                          client_message_id=uuid4(), request_hash="c" * 64)
        session.add(message)
        session.flush()
        session.add(MessageJob(tenant_id=tenant.id, message_id=message.id, conversation_id=conversation.id,
                               created_at=now, available_at=now))
        session.commit()
    assert MessageWorker(database_engine, Settings(environment="test")).claim_one() is None


def test_queued_turn_includes_reply_published_after_it_was_sent(database_engine):
    with Session(database_engine) as session:
        tenant, customer, conversation, first, job, _ = seed_message(session)
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        first.created_at = start
        second = Message(tenant_id=tenant.id, conversation_id=conversation.id,
                         author_kind="CUSTOMER", author_customer_id=customer.id, visibility="PUBLIC",
                         content=[{"type": "text", "text": "那第二步呢？"}], created_at=start + timedelta(seconds=1),
                         client_message_id=uuid4(), request_hash="d" * 64)
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id, message_id=first.id,
                       thread_id=str(uuid4()), lease_token=uuid4(), provider="test", model="test", status="COMPLETED")
        session.add_all([second, run])
        session.flush()
        reply = Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="AGENT",
                        visibility="PUBLIC", content=[{"type": "text", "text": "第一步断电，第二步只检查外观。"}],
                        created_at=start + timedelta(seconds=2), client_message_id=run.id, request_hash="e" * 64)
        later = Message(tenant_id=tenant.id, conversation_id=conversation.id,
                        author_kind="CUSTOMER", author_customer_id=customer.id, visibility="PUBLIC",
                        content=[{"type": "text", "text": "未来一轮，不应读到"}],
                        created_at=start + timedelta(seconds=3), client_message_id=uuid4(), request_hash="f" * 64)
        session.add_all([reply, later])
        session.flush()
        context = AgentContextBuilder(session, tenant.id).build(conversation.id, second.id)
        ids = [entry['message_id'] for entry in context['public_history']]
        assert ids == [str(first.id), str(reply.id)]


def test_context_excludes_internal_messages_and_candidate_facts(database_engine):
    with Session(database_engine) as session:
        tenant, customer, conversation, message, _, case = seed_message(session, with_case=True)
        device = DevicePassport(tenant_id=tenant.id, customer_id=customer.id, model="A1229",
                                identity_source="user_statement")
        session.add(device)
        session.flush()
        session.add(CaseDevice(tenant_id=tenant.id, case_id=case.id, device_id=device.id,
                               role="AFFECTED", is_primary=True))
        session.add_all([
            DeviceFact(tenant_id=tenant.id, device_id=device.id, source_case_id=case.id,
                       fact_key="port", value="USB-A", source_kind="HUMAN", source="staff",
                       validity="VERIFIED", verifier_kind="HUMAN", verified_by="staff:test",
                       verified_at=datetime.now(timezone.utc), archived_at=datetime.now(timezone.utc)),
            DeviceFact(tenant_id=tenant.id, device_id=device.id, source_case_id=case.id,
                       fact_key="guess", value="unsupported", source_kind="MODEL", source="agent",
                       validity="CANDIDATE"),
            Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="AGENT",
                    visibility="INTERNAL", content=[{"type": "text", "text": "DO NOT LEAK INTERNAL NOTE"}]),
        ])
        session.flush()
        context = AgentContextBuilder(session, tenant.id).build(conversation.id, message.id)
        text = str(context)
        assert "A1229" in text and "USB-A" in text
        assert "unsupported" not in text and "DO NOT LEAK INTERNAL NOTE" not in text
        assert context["linked_cases"][0]["id"] == str(case.id)


@pytest.mark.parametrize("same_timestamp", [False, True])
def test_context_history_stops_before_the_current_customer_turn(database_engine, same_timestamp):
    from uuid import UUID

    with Session(database_engine) as session:
        tenant, customer, conversation, message, _, _ = seed_message(session)
        before = Message(
            id=UUID(int=message.id.int - 1), tenant_id=tenant.id, conversation_id=conversation.id,
            author_kind="CUSTOMER", author_customer_id=customer.id, visibility="PUBLIC",
            content=[{"type": "text", "text": "previous customer turn"}],
            created_at=message.created_at if same_timestamp else message.created_at - timedelta(seconds=1),
        )
        after = Message(
            id=UUID(int=message.id.int + 1), tenant_id=tenant.id, conversation_id=conversation.id,
            author_kind="CUSTOMER", author_customer_id=customer.id, visibility="PUBLIC",
            content=[{"type": "text", "text": "future customer turn"}],
            created_at=message.created_at if same_timestamp else message.created_at + timedelta(seconds=1),
        )
        session.add_all([before, after])
        session.flush()
        context = AgentContextBuilder(session, tenant.id).build(conversation.id, message.id)
        assert len(context["public_history"]) == 1
        assert context["public_history"][0]["author"] == "CUSTOMER"
        assert context["public_history"][0]["text"] == "previous customer turn"
        assert context["public_history"][0]["message_id"] == str(before.id)


def test_context_memory_rolls_forward_with_public_source_ids(database_engine):
    with Session(database_engine) as session:
        tenant, customer, conversation, source_message, source_job, _ = seed_message(session)
        now = datetime.now(timezone.utc)
        source_message.created_at = now - timedelta(minutes=10)
        source_run = AgentRun(
            tenant_id=tenant.id, job_id=source_job.id, conversation_id=conversation.id,
            message_id=source_message.id, thread_id=str(uuid4()), lease_token=uuid4(),
            provider="test", model="test", result_payload={
                "context_memory": {"method": "extractive_with_sources", "items": [{
                    "message_id": str(source_message.id), "author": "CUSTOMER",
                    "created_at": source_message.created_at.isoformat(), "excerpt": "早先报告没有充电",
                }]},
            },
        )
        session.add(source_run)
        for index in range(205):
            session.add(Message(
                tenant_id=tenant.id, conversation_id=conversation.id, author_kind="CUSTOMER",
                author_customer_id=customer.id, visibility="PUBLIC",
                content=[{"type": "text", "text": f"历史轮次 {index} " + "排查记录 " * 80}],
                created_at=now - timedelta(seconds=205 - index),
            ))
        current = Message(
            tenant_id=tenant.id, conversation_id=conversation.id, author_kind="CUSTOMER",
            author_customer_id=customer.id, visibility="PUBLIC",
            content=[{"type": "text", "text": "现在应该怎么继续排查？"}],
            created_at=now,
        )
        session.add(current)
        session.flush()
        context = AgentContextBuilder(session, tenant.id).build(
            conversation.id, current.id, run_id=uuid4(),
        )
        assert all(row["message_id"] != str(source_message.id) for row in context["public_history"])
        assert any(row["message_id"] == str(source_message.id)
                   for row in context["context_memory"]["items"])
        assert context["context_budget"]["estimated_tokens"] <= context["context_budget"]["token_budget"] + 80


def test_outbox_dispatch_is_transactional_and_idempotent(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, _, _, _ = seed_message(session)
        event = OutboxEvent(tenant_id=tenant.id, conversation_id=conversation.id,
                            type="message.created", visibility="PUBLIC", data={"message_id": "m-1"})
        session.add(event)
        session.commit()
        event_id = event.id
        conversation_id = conversation.id
        tenant_id = tenant.id

    dispatcher = OutboxDispatcher(database_engine, worker_id="outbox-test")
    leases = dispatcher.claim_batch()
    assert len(leases) >= 1
    lease = next(item for item in leases if item.item_id == event_id)
    assert dispatcher.dispatch(lease) is True
    assert dispatcher.dispatch(lease) is False
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(ConversationEvent).where(
            ConversationEvent.tenant_id == tenant_id,
            ConversationEvent.conversation_id == conversation_id,
            ConversationEvent.data["message_id"].astext == "m-1",
        )) == 1
        row = session.get(OutboxEvent, event_id)
        assert row.published_at is not None and row.lease_token is None


def test_worker_failure_is_sanitized_and_retriable(database_engine):
    class FailingRuntime:
        configured = True

        def invoke(self, **_):
            raise RuntimeError("provider error response included sensitive data")

    with Session(database_engine) as session:
        _, _, _, _, job, _ = seed_message(session)
        session.commit()
        job_id = job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=FailingRuntime())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        assert job.status == "QUEUED" and job.attempt_count == 1
        assert job.last_error_code == "agent_execution_failed"
        assert "sensitive" not in job.last_error_code
        assert job.lease_token is None
        assert run.status == "FAILED" and run.error_code == "agent_execution_failed"


def test_worker_marks_failure_terminal_at_configured_attempt_limit(database_engine):
    class FailingRuntime:
        configured = True

        def invoke(self, **_):
            raise RuntimeError("private provider response")

    with Session(database_engine) as session:
        _, _, _, _, job, _ = seed_message(session)
        session.commit()
        job_id = job.id
    settings = Settings(environment="test", worker_max_attempts=1)
    worker = MessageWorker(database_engine, settings, runtime=FailingRuntime())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        assert job.status == "FAILED" and job.attempt_count == 1
        assert job.last_error_code == "agent_execution_failed"


def test_outbox_marks_exhausted_crashed_lease_dead_letter(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, _, _, _ = seed_message(session)
        event = OutboxEvent(
            tenant_id=tenant.id, conversation_id=conversation.id, type="test.event",
            visibility="INTERNAL", data={}, attempt_count=1, max_attempts=1,
            lease_token=uuid4(), lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        session.add(event)
        session.commit()
        event_id = event.id
    dispatcher = OutboxDispatcher(database_engine)
    assert dispatcher.claim_batch() == []
    with Session(database_engine) as session:
        event = session.get(OutboxEvent, event_id)
        assert event.dead_lettered_at is not None
        assert event.last_error_code == "lease_expired_max_attempts"


def test_conversation_dispatcher_does_not_ack_unrouted_outbox_events(database_engine):
    with Session(database_engine) as session:
        tenant, _, _, _, _, _ = seed_message(session)
        event = OutboxEvent(tenant_id=tenant.id, conversation_id=None,
                            type="case.updated", visibility="INTERNAL", data={"case_id": "c-1"})
        session.add(event)
        session.commit()
        event_id = event.id
    assert OutboxDispatcher(database_engine).claim_batch() == []
    with Session(database_engine) as session:
        event = session.get(OutboxEvent, event_id)
        assert event.published_at is None and event.attempt_count == 0


def test_worker_success_publishes_through_conversation_service(database_engine):
    class SuccessfulRuntime:
        configured = True

        def invoke(self, **_):
            return "请确认设备型号，并尝试更换一条可靠线材。", {
                "step_count": 2, "input_tokens": 140, "output_tokens": 30,
            }

    with Session(database_engine) as session:
        _, _, conversation, input_message, job, _ = seed_message(session)
        session.commit()
        job_id, conversation_id, input_message_id = job.id, conversation.id, input_message.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=SuccessfulRuntime())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        run = session.scalar(select(AgentRun).where(AgentRun.message_id == input_message_id))
        response = session.scalar(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.author_kind == "AGENT",
            Message.client_message_id == run.id,
        ))
        assert job.status == "COMPLETED" and job.completed_at is not None
        assert run.status == "COMPLETED" and run.step_count == 2
        assert run.input_tokens == 140 and run.output_tokens == 30
        assert response.visibility == "PUBLIC"
        assert response.content[0]["text"].startswith("请确认设备型号")


def test_unconfigured_provider_does_not_claim_jobs(database_engine):
    with Session(database_engine) as session:
        _, _, _, _, job, _ = seed_message(session)
        session.commit()
        job_id = job.id
    worker = MessageWorker(database_engine, Settings(environment="test"))
    with pytest.raises(RuntimeError, match="Configure SERVICEOS_LLM_MODEL"):
        worker.run_once()
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        assert job.status == "QUEUED" and job.attempt_count == 0


def test_agent_publication_rechecks_current_policy(database_engine):
    with Session(database_engine) as session:
        tenant, customer, conversation, message, job, _ = seed_message(session)
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(conversation.id), lease_token=uuid4(),
                       provider="test", model="test-only", result_text="基于现有资料的建议")
        session.add(run)
        session.flush()
        first = ConversationService(session, Principal(tenant.id, customer.id, "CUSTOMER", "客户"), settings=Settings(environment="test")).publish_agent_response(
            tenant.id, conversation.id, run.id, run.lease_token, "基于现有资料的建议", None,
        )
        assert first.visibility == "PUBLIC"
        internal_job = MessageJob(tenant_id=tenant.id, message_id=message.id, conversation_id=conversation.id,
                                  status="QUEUED")
        # The real schema permits only one job per input; use a second input for the internal result.
        internal_message = Message(tenant_id=tenant.id, conversation_id=conversation.id,
                                   author_kind="CUSTOMER", author_customer_id=customer.id,
                                   visibility="PUBLIC", content=[{"type": "text", "text": "follow up"}],
                                   client_message_id=uuid4(), request_hash="b" * 64)
        session.add(internal_message)
        session.flush()
        internal_job.message_id = internal_message.id
        session.add(internal_job)
        session.flush()
        second_run = AgentRun(tenant_id=tenant.id, job_id=internal_job.id, conversation_id=conversation.id,
                              message_id=internal_message.id, thread_id=str(conversation.id),
                              lease_token=uuid4(), provider="test", model="test-only")
        conversation.collaboration_mode = "HUMAN_LEAD"
        conversation.reply_policy = "HUMAN_ONLY"
        session.add(second_run)
        session.flush()
        second = ConversationService(session, Principal(tenant.id, customer.id, "CUSTOMER", "客户"), settings=Settings(environment="test")).publish_agent_response(
            tenant.id, conversation.id, second_run.id, second_run.lease_token, "内部草稿", None,
        )
        assert second.visibility == "INTERNAL"
        assert session.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation.id, Message.visibility == "INTERNAL",
        )) == 1


def test_rejected_action_proposal_remains_internal_and_does_not_execute(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(conversation.id), lease_token=uuid4(),
                       provider="test", model="test-only")
        session.add(run)
        session.flush()
        proposal = AgentProposal(tenant_id=tenant.id, conversation_id=conversation.id,
                                 agent_run_id=run.id, proposal_type="ACTION", idempotency_key="review-test",
                                 payload={"summary": "模拟售后动作草稿"})
        session.add(proposal)
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        session.flush()
        principal = Principal(tenant.id, staff.id, "STAFF", staff.display_name, "SUPPORT")
        service = ConversationService(session, principal)
        request = ProposalDecision(decision_id=uuid4(), decision="REJECTED", reason="缺少用户证据")
        first = service.decide_proposal(proposal.id, request)
        assert first.status == "REJECTED"
        assert service.decide_proposal(proposal.id, request).status == "REJECTED"
        with pytest.raises(ServiceError) as error:
            service.decide_proposal(proposal.id, ProposalDecision(
                decision_id=uuid4(), decision="APPROVED", reason="重复尝试批准"))
        assert error.value.status == 409
        assert session.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation.id, Message.author_kind == "AGENT",
        )) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.conversation_id == conversation.id, OutboxEvent.type == "action.completed",
        )) == 0


def test_reply_draft_approval_rechecks_mode_and_publishes_once(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        conversation.collaboration_mode = "CO_SERVICE"
        conversation.reply_policy = "AI_REVIEW_REQUIRED"
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(conversation.id), lease_token=uuid4(),
                       provider="test", model="test-only")
        session.add(run)
        session.flush()
        draft = ConversationService(session, actor=None, settings=Settings(environment="test")).publish_agent_response(
            tenant.id, conversation.id, run.id, run.lease_token, "请补充接口照片")
        assert draft.visibility == "INTERNAL"
        proposal = session.scalar(select(AgentProposal).where(
            AgentProposal.agent_run_id == run.id, AgentProposal.proposal_type == "REPLY"))
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        service = ConversationService(session, Principal(tenant.id, staff.id, "STAFF", staff.display_name, "SUPPORT"))
        request = ProposalDecision(decision_id=uuid4(), decision="APPROVED", reason="内容已核对")
        assert service.decide_proposal(proposal.id, request).status == "APPROVED"
        assert service.decide_proposal(proposal.id, request).status == "APPROVED"
        public = session.scalars(select(Message).where(
            Message.conversation_id == conversation.id, Message.visibility == "PUBLIC",
            Message.author_kind == "AGENT")).all()
        assert len(public) == 1 and public[0].content == draft.content

    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        conversation.collaboration_mode = "HUMAN_LEAD"
        conversation.reply_policy = "HUMAN_ONLY"
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(conversation.id), lease_token=uuid4(),
                       provider="test", model="test-only")
        session.add(run)
        session.flush()
        ConversationService(session, actor=None, settings=Settings(environment="test")).publish_agent_response(
            tenant.id, conversation.id, run.id, run.lease_token, "仅作内部工作")
        proposal = session.scalar(select(AgentProposal).where(
            AgentProposal.agent_run_id == run.id, AgentProposal.proposal_type == "REPLY"))
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        service = ConversationService(session, Principal(tenant.id, staff.id, "STAFF", staff.display_name, "SUPPORT"))
        with pytest.raises(ServiceError) as error:
            service.decide_proposal(proposal.id, ProposalDecision(
                decision_id=uuid4(), decision="APPROVED", reason="试图公开旧草稿"))
        assert error.value.status == 409
        assert service.decide_proposal(proposal.id, ProposalDecision(
            decision_id=uuid4(), decision="REJECTED", reason="人工主导不公开")).status == "REJECTED"
        assert session.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation.id, Message.visibility == "PUBLIC",
            Message.author_kind == "AGENT")) == 0


def test_worker_persists_separated_result_and_only_internal_action_reference(database_engine):
    class ProposalRuntime:
        configured = True

        def invoke(self, **kwargs):
            with Session(database_engine) as session:
                service = AgentToolService(session, kwargs["tenant_id"], kwargs["conversation_id"],
                                           kwargs["run_id"], kwargs["lease_token"],
                                           settings=Settings(environment="test"))
                service.record_proposal("ACTION", "请客服审核模拟换货申请")
                service.record_proposal("ACTION", "请客服审核模拟换货申请")
            return AgentResult("请先确认设备型号。", {
                "purpose": "确认型号", "audience": "CUSTOMER",
                "fallback_text": "请用文字说明型号。", "component_hints": ["QuestionForm"],
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        session.commit()
        tenant_id, conversation_id, job_id = tenant.id, conversation.id, job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=ProposalRuntime())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        proposals = session.scalars(select(AgentProposal).where(AgentProposal.agent_run_id == run.id)).all()
        response = session.scalar(select(Message).where(Message.client_message_id == run.id))
        assert run.status == "COMPLETED"
        assert run.result_payload["ui_proposal"]["purpose"] == "确认型号"
        assert run.result_payload["action_proposals"] == [str(proposals[0].id)]
        assert len(proposals) == 1 and proposals[0].visibility == "INTERNAL"
        assert response.visibility == "PUBLIC" and response.content == [{"type": "text", "text": "请先确认设备型号。"}]
        assert session.scalar(select(func.count()).select_from(Message).where(
            Message.tenant_id == tenant_id, Message.conversation_id == conversation_id,
            Message.author_kind == "AGENT",
        )) == 1


def test_worker_reuses_persisted_result_and_rechecks_policy(database_engine):
    class MustNotRun:
        configured = True

        def invoke(self, **_):
            raise AssertionError("saved result must be reused")

    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        conversation.collaboration_mode = "HUMAN_LEAD"
        conversation.reply_policy = "HUMAN_ONLY"
        run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                       message_id=message.id, thread_id=str(conversation.id), lease_token=uuid4(),
                       status="FAILED", provider="test", model="test", result_text="内部建议",
                       result_payload={"schema_version": 1, "ui_proposal": None,
                                       "ui_fallback_code": "ui_proposal_invalid", "action_proposals": []})
        session.add(run)
        session.commit()
        job_id = job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=MustNotRun())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        response = session.scalar(select(Message).where(Message.client_message_id == run.id))
        assert run.status == "COMPLETED" and run.result_payload["ui_fallback_code"] == "ui_proposal_invalid"
        assert response.visibility == "INTERNAL"


def test_old_lease_cannot_store_agent_result(database_engine):
    class StealLease:
        configured = True

        def invoke(self, **kwargs):
            with Session(database_engine) as session:
                session.execute(update(AgentRun).where(AgentRun.id == kwargs["run_id"]).values(lease_token=uuid4()))
                session.commit()
            return AgentResult("旧租约结果"), {"step_count": 1}

    with Session(database_engine) as session:
        _, _, _, _, job, _ = seed_message(session)
        session.commit()
        job_id = job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=StealLease())
    lease = worker.claim_one()
    assert lease is not None
    worker.process(lease)
    with Session(database_engine) as session:
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        # The agent result itself must not be stored. The context snapshot is different: a lease
        # that was still valid computed it before the takeover and it carries no agent output.
        assert run.result_text is None
        assert set(run.result_payload or {}) <= {"context_memory"}
        assert session.scalar(select(func.count()).select_from(Message).where(Message.client_message_id == run.id)) == 0


def test_expired_job_lease_cannot_create_action_proposal(database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, _ = seed_message(session)
        session.commit()
        tenant_id, conversation_id, message_id, job_id = tenant.id, conversation.id, message.id, job.id
    worker = MessageWorker(database_engine, Settings(environment="test"))
    lease = worker.claim_one()
    assert lease is not None
    with Session(database_engine) as session:
        run = AgentRun(tenant_id=tenant_id, job_id=job_id, conversation_id=conversation_id,
                       message_id=message_id, thread_id=str(conversation_id),
                       lease_token=lease.token, provider="test", model="test")
        session.add(run)
        session.flush()
        run_id = run.id
        session.execute(update(MessageJob).where(MessageJob.id == job_id).values(
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        session.commit()
    with Session(database_engine) as session:
        service = AgentToolService(session, tenant_id, conversation_id, run_id, lease.token)
        with pytest.raises(ValueError, match="agent_run_lease_lost"):
            service.record_proposal("ACTION", "stale request")
        assert session.scalar(select(func.count()).select_from(AgentProposal).where(
            AgentProposal.agent_run_id == run_id)) == 0


@pytest.mark.parametrize("mode,policy,visibility", [
    ("AI_LEAD", "AI_AUTO", "PUBLIC"),
    ("CO_SERVICE", "AI_REVIEW_REQUIRED", "INTERNAL"),
    ("HUMAN_LEAD", "HUMAN_ONLY", "INTERNAL"),
])
def test_worker_real_progress_and_skill_audit_survive_result_storage(database_engine, mode, policy, visibility):
    class SkillRuntime:
        configured = True

        def invoke(self, **kwargs):
            with Session(database_engine) as session:
                service = AgentToolService(session, kwargs["tenant_id"], kwargs["conversation_id"],
                                           kwargs["run_id"], kwargs["lease_token"],
                                           settings=Settings(environment="test"))
                service.load_skill("diagnose-no-charge", "1.0.0")
                # Retrieval returns verbatim manual paragraphs, so a matching query word does
                # appear in the result. What must never come back is arbitrary caller text.
                lookup = service.lookup_manual("不充电 SECRET TOOL ARGUMENT").to_prompt_text()
                assert "SOURCE:" in lookup
                assert "SECRET TOOL ARGUMENT" not in lookup
                service.lookup_manual("unknown private query SECRET RETRY")
                service.record_proposal("MISSING_EVIDENCE", "INTERNAL DRAFT")
            return AgentResult("请确认型号。"), {"step_count": 3}

    with Session(database_engine) as session:
        _, _, conversation, _, job, _ = seed_message(session)
        conversation.collaboration_mode, conversation.reply_policy = mode, policy
        session.commit()
        conversation_id, job_id = conversation.id, job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=SkillRuntime())
    lease = worker.claim_one()
    worker.process(lease)
    worker.process(lease)  # A stale retry cannot generate another logical progress event.
    with Session(database_engine) as session:
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        assert run.status == "COMPLETED"
        assert run.result_payload["skill_executions"][0]["status"] == "LOADED"
        events = session.scalars(select(OutboxEvent).where(
            OutboxEvent.conversation_id == conversation_id, OutboxEvent.type == "agent.progress",
        ).order_by(OutboxEvent.created_at, OutboxEvent.id)).all()
        assert sorted(row.data["stage"] for row in events) == ["COMPLETED", "LOOKUP", "LOOKUP", "LOOKUP", "RUNNING", "RUNNING"]
        assert all(row.visibility == visibility for row in events)
        assert all(set(row.data) == {"run_id", "stage", "summary"} for row in events)
        assert all("SECRET" not in str(row.data) and "INTERNAL DRAFT" not in str(row.data) for row in events)
        assert not any(row.data["stage"].startswith("WAITING") for row in events)
        for event in events:
            ConversationService.dispatch_outbox_event(session, event)
        session.commit()
        customer = session.get(Conversation, conversation_id).customer_id
        public = ConversationService(session, Principal(run.tenant_id, customer, "CUSTOMER", "客户")).events(conversation_id)
        assert len(public.items) == (6 if visibility == "PUBLIC" else 0)


def test_progress_rechecks_mode_on_dispatch_and_rejects_unknown_fields(db_session):
    from test_skills import active_skill_run

    tenant, _, conversation, _, _, run = active_skill_run(db_session)
    event = ConversationService.record_agent_progress(
        db_session, tenant.id, conversation.id, run.id, run.lease_token, "worker_started")
    db_session.flush()
    assert event.visibility == "PUBLIC"
    assert ConversationService.record_agent_progress(
        db_session, tenant.id, conversation.id, run.id, run.lease_token, "worker_started").id == event.id
    conversation.collaboration_mode, conversation.reply_policy = "HUMAN_LEAD", "HUMAN_ONLY"
    db_session.flush()
    published = ConversationService.dispatch_outbox_event(db_session, event)
    db_session.flush()
    assert published.visibility == "INTERNAL"
    assert ConversationService.dispatch_outbox_event(db_session, event).id == published.id
    for data in (dict(event.data, raw_reasoning="private"), dict(event.data, summary="model guess"),
                 dict(event.data, stage="THINKING"), dict(event.data, run_id=str(uuid4()))):
        forged = OutboxEvent(tenant_id=tenant.id, conversation_id=conversation.id,
                             type="agent.progress", visibility="PUBLIC", data=data)
        with pytest.raises(ServiceError):
            ConversationService.dispatch_outbox_event(db_session, forged)


def test_specialist_activity_is_idempotent_allowlisted_and_policy_rechecked(db_session):
    from test_skills import active_skill_run
    from serviceos_api.persistence.models import DiagnosticTask, SpecialistRun

    tenant, customer, conversation, message, _, parent = active_skill_run(db_session)
    task = DiagnosticTask(tenant_id=tenant.id, conversation_id=conversation.id, source_message_id=message.id,
                          parent_agent_run_id=parent.id, idempotency_key="a" * 64, status="RUNNING", version=1,
                          input_payload={"task_id": str(uuid4())})
    db_session.add(task)
    db_session.flush()
    specialist = SpecialistRun(tenant_id=tenant.id, diagnostic_task_id=task.id, parent_agent_run_id=parent.id,
                              checkpoint_thread_id=f"diagnostic:{uuid4()}", attempt=1, status="RUNNING",
                              lease_token=parent.lease_token)
    db_session.add(specialist)
    db_session.flush()
    event = ConversationService.record_specialist_event(
        db_session, tenant.id, conversation.id, parent.id, parent.lease_token, task.id, specialist.id, "STARTED")
    assert ConversationService.record_specialist_event(
        db_session, tenant.id, conversation.id, parent.id, parent.lease_token, task.id, specialist.id, "STARTED").id == event.id
    assert event.visibility == "PUBLIC"
    conversation.collaboration_mode, conversation.reply_policy = "CO_SERVICE", "AI_AUTO"
    db_session.flush()
    published = ConversationService.dispatch_outbox_event(db_session, event)
    assert published.data["display_name"] == "诊断专家"
    assert published.data["stage"] == "STARTED"
    assert published.visibility == "INTERNAL"
    from serviceos_api.application.auth import Principal

    customer_view = ConversationService(db_session, Principal(tenant.id, customer.id, "CUSTOMER", "客户"))
    staff_view = ConversationService(db_session, Principal(tenant.id, uuid4(), "STAFF", "客服", "SUPPORT"))
    assert not customer_view.events(conversation.id).items
    assert staff_view.events(conversation.id).items[-1].type == "specialist.activity"
    forged = OutboxEvent(tenant_id=tenant.id, conversation_id=conversation.id, type="specialist.activity",
                         visibility="PUBLIC", data=dict(event.data, raw_reasoning="secret"))
    with pytest.raises(ServiceError):
        ConversationService.dispatch_outbox_event(db_session, forged)


def test_specialist_result_event_never_claims_verified_fact(db_session):
    from test_skills import active_skill_run
    from serviceos_api.application.agent_services import AgentToolService
    from serviceos_api.application.diagnostic_contracts import DiagnosticResult, DiagnosticTaskInput
    from serviceos_api.persistence.models import DiagnosticTask, SpecialistRun

    tenant, _, conversation, message, _, parent = active_skill_run(db_session)
    task_input = DiagnosticTaskInput(task_id=uuid4(), conversation_id=conversation.id, goal="分析供电问题")
    task = DiagnosticTask(tenant_id=tenant.id, conversation_id=conversation.id, source_message_id=message.id,
                          parent_agent_run_id=parent.id, idempotency_key="b" * 64, status="RUNNING", version=1,
                          input_payload=task_input.model_dump(mode="json"))
    db_session.add(task)
    db_session.flush()
    task_input = task_input.model_copy(update={"task_id": task.id})
    task.input_payload = task_input.model_dump(mode="json")
    specialist = SpecialistRun(tenant_id=tenant.id, diagnostic_task_id=task.id, parent_agent_run_id=parent.id,
                              checkpoint_thread_id=f"diagnostic:{uuid4()}", attempt=1, status="RUNNING",
                              lease_token=parent.lease_token)
    db_session.add(specialist)
    db_session.flush()
    result = DiagnosticResult(task_id=task.id, assessment="可能是供电连接问题", next_step={"kind": "ASK_CUSTOMER", "summary": "确认充电器", "question": {"prompt": "充电器指示灯是否亮起？"}}, staff_summary="待核验假设")
    payload = AgentToolService(db_session, tenant.id, conversation.id, parent.id, parent.lease_token).complete_diagnostic(
        task.id, specialist.id, result, {}, task_input)
    events = db_session.scalars(select(OutboxEvent).where(
        OutboxEvent.conversation_id == conversation.id, OutboxEvent.type == "specialist.activity")).all()
    ready = next(event for event in events if event.data["stage"] == "RESULT_READY")
    published = ConversationService.dispatch_outbox_event(db_session, ready)
    assert payload["certainty"] == "HYPOTHESIS"
    assert published.data["certainty"] == "HYPOTHESIS"
    assert "待核验" in published.data["summary"]


@pytest.mark.parametrize(("kind", "expected"), [
    ("SAFETY_STOP", "请先停止使用和测试设备"),
    ("HUMAN_REVIEW", "当前信息需要人工客服进一步核实"),
])
def test_sop_safety_and_human_review_override_freeform_agent_reply(db_session, kind, expected):
    from test_skills import active_skill_run
    from serviceos_api.persistence.models import DiagnosticTask

    tenant, _, conversation, message, _, run = active_skill_run(db_session)
    task = DiagnosticTask(
        tenant_id=tenant.id, conversation_id=conversation.id, source_message_id=message.id,
        parent_agent_run_id=run.id, idempotency_key="d" * 64, status="WAITING_STAFF", version=2,
        input_payload={"task_id": str(uuid4())},
        result_payload={"next_step": {"kind": kind}},
    )
    db_session.add(task)
    db_session.flush()
    published = ConversationService(db_session, actor=None, settings=Settings(environment="test")).publish_agent_response(
        tenant.id, conversation.id, run.id, run.lease_token,
        "UNSAFE MODEL TEXT: continue testing and the problem is solved.",
    )
    text = published.content[0]["text"]
    assert expected in text
    assert "UNSAFE MODEL TEXT" not in text and "已解决" not in text


def test_progress_generation_rejects_stale_lease_and_false_completion(db_session):
    from test_skills import active_skill_run

    tenant, _, conversation, _, job, run = active_skill_run(db_session)
    with pytest.raises(ValueError):
        ConversationService.record_agent_progress(db_session, tenant.id, conversation.id, run.id,
                                                   run.lease_token, "worker_completed")
    job.lease_token = uuid4()
    db_session.flush()
    with pytest.raises(ValueError):
        ConversationService.record_agent_progress(db_session, tenant.id, conversation.id, run.id,
                                                   run.lease_token, "worker_started")
    assert not db_session.scalars(select(OutboxEvent).where(
        OutboxEvent.conversation_id == conversation.id, OutboxEvent.type == "agent.progress")).all()


def test_failure_progress_is_fixed_and_retry_creates_fenced_new_attempt(database_engine):
    class FailingRuntime:
        configured = True

        def invoke(self, **_):
            raise RuntimeError("SECRET PROVIDER ERROR")

    with Session(database_engine) as session:
        _, _, conversation, _, job, _ = seed_message(session)
        session.commit()
        conversation_id, job_id = conversation.id, job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=FailingRuntime())
    first = worker.claim_one()
    worker.process(first)
    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    second = worker.claim_one()
    assert second.token != first.token
    worker.process(second)
    with Session(database_engine) as session:
        events = session.scalars(select(OutboxEvent).where(
            OutboxEvent.conversation_id == conversation_id, OutboxEvent.type == "agent.progress")).all()
        assert sorted(row.data["stage"] for row in events) == ["FAILED", "FAILED", "RUNNING", "RUNNING"]
        assert all("SECRET" not in str(row.data) for row in events)


def test_agent_output_format_failure_is_terminal_without_job_retry(database_engine):
    class InvalidOutputRuntime:
        configured = True

        def invoke(self, **_):
            raise AgentOutputInvalidError("agent_output_invalid")

    with Session(database_engine) as session:
        _, _, conversation, _, job, _ = seed_message(session)
        session.commit()
        conversation_id, job_id = conversation.id, job.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=InvalidOutputRuntime())
    lease = worker.claim_one()
    worker.process(lease)

    with Session(database_engine) as session:
        job = session.get(MessageJob, job_id)
        run = session.scalar(select(AgentRun).where(AgentRun.job_id == job_id))
        event = session.scalar(select(OutboxEvent).where(
            OutboxEvent.conversation_id == conversation_id, OutboxEvent.type == "agent.progress",
            OutboxEvent.data["stage"].as_string() == "FAILED",
        ))
        assert job.status == "FAILED" and job.attempt_count == 1
        assert job.last_error_code == "agent_output_invalid"
        assert run.status == "FAILED" and run.error_code == "agent_output_invalid"
        assert event is not None
        assert worker.claim_one() is None


def test_customer_projection_renders_agent_options_as_a_choice_group(database_engine):
    """The projection must read the proposal instead of always emitting a plain QuestionForm."""
    options = [{"label": "指示灯完全不亮", "value": "no-light"}, {"label": "指示灯常亮", "value": "steady"}]

    class ChoiceRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("指示灯现在是什么状态？", {
                "purpose": "确认指示灯状态", "audience": "CUSTOMER",
                "fallback_text": "也可用文字说明。", "component_hints": ["ChoiceGroup"],
                "options": options,
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, customer, conversation, _, _, _ = seed_message(session)
        session.commit()
        tenant_id, customer_id, conversation_id = tenant.id, customer.id, conversation.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=ChoiceRuntime())
    worker.process(worker.claim_one())

    with Session(database_engine) as session:
        principal = Principal(tenant_id, customer_id, "CUSTOMER", "客户")
        projected = ConversationService(session, principal).publish_ui_projection(conversation_id)
        assert projected.catalog_version == 3
        assert projected.components[0].type == "ActionBar", "the assistance action stays first"
        choice = next(item for item in projected.components if item.type == "ChoiceGroup")
        assert choice.id == "agent-choice"
        assert [item.label for item in choice.options] == [option["label"] for option in options]
        assert choice.actions == [], "a choice is a message, not a new action surface"


def test_customer_projection_without_options_keeps_the_question_form(database_engine):
    class QuestionRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("请说明充电头的功率。", {
                "purpose": "补充充电头规格", "audience": "CUSTOMER",
                "fallback_text": "也可用文字说明。", "component_hints": ["QuestionForm"],
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, customer, conversation, _, _, _ = seed_message(session)
        session.commit()
        tenant_id, customer_id, conversation_id = tenant.id, customer.id, conversation.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=QuestionRuntime())
    worker.process(worker.claim_one())

    with Session(database_engine) as session:
        principal = Principal(tenant_id, customer_id, "CUSTOMER", "客户")
        projected = ConversationService(session, principal).publish_ui_projection(conversation_id)
        kinds = [item.type for item in projected.components]
        assert "ChoiceGroup" not in kinds
        question = next(item for item in projected.components if item.type == "QuestionForm")
        assert question.options == []


def test_customer_projection_builds_metric_from_verified_model_and_curated_source(database_engine):
    class MetricRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("加热功能的额外电量消耗约为以下数值。", {
                "purpose": "解释加热功能的额外电量消耗", "audience": "CUSTOMER",
                "fallback_text": "可按文字查看近似估算。", "component_hints": ["KnowledgeMetricChart"],
                "knowledge_source_id": "eufy-s1-pro-heating-battery-v1",
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, customer, conversation, _, _, case = seed_message(session, with_case=True)
        device = DevicePassport(tenant_id=tenant.id, customer_id=customer.id, model="T8D04",
                                identity_source="staff_verified", identity_status="VERIFIED",
                                verified_by="客服核验", verified_at=datetime.now(timezone.utc))
        session.add(device)
        session.flush()
        session.add(CaseDevice(tenant_id=tenant.id, case_id=case.id, device_id=device.id,
                               role="AFFECTED", is_primary=True))
        session.commit()
        tenant_id, customer_id, conversation_id = tenant.id, customer.id, conversation.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=MetricRuntime())
    worker.process(worker.claim_one())

    with Session(database_engine) as session:
        projected = ConversationService(session, Principal(tenant_id, customer_id, "CUSTOMER", "客户")) \
            .publish_ui_projection(conversation_id)
        assert projected.catalog_version == 3
        chart = next(item for item in projected.components if item.type == "KnowledgeMetricChart")
        assert [point.model_dump() for point in chart.chart.points] == [
            {"label": "5 分钟", "value": 10.0}, {"label": "10 分钟", "value": 20.0},
            {"label": "15 分钟", "value": 30.0},
        ]
        assert chart.actions == [] and chart.data_source.kind == "AGENT_RUN_VIEW"


def test_customer_metric_is_suppressed_without_verified_applicable_model(database_engine):
    class MetricRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("以下估算仅适用于核验型号。", {
                "purpose": "解释加热功能的额外电量消耗", "audience": "CUSTOMER",
                "fallback_text": "可阅读文字说明。", "component_hints": ["KnowledgeMetricChart"],
                "knowledge_source_id": "eufy-s1-pro-heating-battery-v1",
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, customer, conversation, _, _, _ = seed_message(session)
        session.commit()
        tenant_id, customer_id, conversation_id = tenant.id, customer.id, conversation.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=MetricRuntime())
    worker.process(worker.claim_one())
    with Session(database_engine) as session:
        projected = ConversationService(session, Principal(tenant_id, customer_id, "CUSTOMER", "客户")) \
            .publish_ui_projection(conversation_id)
        assert all(item.type != "KnowledgeMetricChart" for item in projected.components)


def test_staff_projection_builds_case_flow_from_authorized_linked_case(database_engine):
    class FlowRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("我已整理当前案例办理状态。", {
                "purpose": "查看当前案例的办理进度", "audience": "STAFF",
                "fallback_text": "可直接查看案例状态。", "component_hints": ["CaseProcessFlow"],
                "case_id": str(case_id),
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, _, conversation, _, _, case = seed_message(session, with_case=True)
        seed_local_accounts(session)
        staff = session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        tenant_id, conversation_id, staff_id, case_id = tenant.id, conversation.id, staff.id, case.id
        session.commit()
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=FlowRuntime())
    worker.process(worker.claim_one())

    with Session(database_engine) as session:
        projected = ConversationService(session, Principal(tenant_id, staff_id, "STAFF", "本地客服", "SUPPORT")) \
            .publish_ui_projection(conversation_id)
        flow = next(item for item in projected.components if item.type == "CaseProcessFlow")
        assert projected.audience == "STAFF" and projected.visibility == "INTERNAL"
        assert flow.flow.nodes[0].resource_id == case_id
        assert flow.flow.nodes[0].status == "IN_PROGRESS"
        assert flow.actions == []


def test_an_answered_question_is_not_projected_again(database_engine):
    """The card kept asking the same question: once the customer replies, that question is
    answered, and an older run's proposal must not be resurrected from the lookback window."""

    class ChoiceRuntime:
        configured = True

        def invoke(self, **_):
            return AgentResult("请确认指示灯状态。", {
                "purpose": "确认指示灯状态", "audience": "CUSTOMER", "fallback_text": "也可用文字说明。",
                "component_hints": ["ChoiceGroup"],
                "options": [{"label": "完全不亮", "value": "no-light"}, {"label": "常亮", "value": "steady"}],
            }), {"step_count": 1}

    with Session(database_engine) as session:
        tenant, customer, conversation, _, _, _ = seed_message(session)
        session.commit()
        tenant_id, customer_id, conversation_id = tenant.id, customer.id, conversation.id
    worker = MessageWorker(database_engine, Settings(environment="test"), runtime=ChoiceRuntime())
    worker.process(worker.claim_one())
    principal = Principal(tenant_id, customer_id, "CUSTOMER", "客户")

    with Session(database_engine) as session:
        first = ConversationService(session, principal).publish_ui_projection(conversation_id)
        assert any(item.type == "ChoiceGroup" for item in first.components), "the question is projected while it is open"

    with Session(database_engine) as session:
        session.add(Message(tenant_id=tenant_id, conversation_id=conversation_id, author_kind="CUSTOMER",
                            author_customer_id=customer_id, visibility="PUBLIC",
                            content=[{"type": "text", "text": "完全不亮"}], client_message_id=uuid4(),
                            request_hash="b" * 64))
        session.commit()

    with Session(database_engine) as session:
        answered = ConversationService(session, principal).publish_ui_projection(conversation_id)
        assert [item.type for item in answered.components] == ["ActionBar"], \
            "an answered question must not come back"
