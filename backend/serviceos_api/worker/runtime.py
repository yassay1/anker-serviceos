"""PostgreSQL lease-based processing and transactional Outbox dispatch."""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from serviceos_api.application.agent_services import AgentContextBuilder
from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import ConversationService
from serviceos_api.agents.runtime import AgentRuntime
from serviceos_api.agents.result import AgentResult
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import (
    AgentProposal, AgentRun, Conversation, Message, MessageJob, OutboxEvent,
)
from serviceos_api.settings import Settings

logger = logging.getLogger("serviceos.worker")

# Single source of truth for the container healthcheck role of the combined agent worker.
ROLE = "agent"


@dataclass(frozen=True)
class Lease:
    tenant_id: UUID
    item_id: UUID
    token: UUID


class MessageWorker:
    def __init__(self, engine, settings: Settings, runtime: AgentRuntime | None = None,
                 worker_id: str | None = None):
        self.engine = engine
        self.settings = settings
        self.runtime = runtime or AgentRuntime(settings)
        self.worker_id = worker_id or f"worker-{uuid4()}"

    def claim_one(self) -> Lease | None:
        now = datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session:
            exhausted = session.scalars(select(MessageJob).where(
                MessageJob.status == "RUNNING",
                MessageJob.lease_expires_at <= now,
                MessageJob.attempt_count >= func.least(MessageJob.max_attempts, self.settings.worker_max_attempts),
            ).with_for_update(skip_locked=True).limit(50)).all()
            for row in exhausted:
                row.status = "FAILED"
                row.last_error_code = "lease_expired_max_attempts"
                row.lease_owner = None
                row.lease_token = None
                row.lease_expires_at = None
                run = session.scalar(select(AgentRun).where(
                    AgentRun.tenant_id == row.tenant_id, AgentRun.job_id == row.id,
                    AgentRun.status != "COMPLETED",
                ).with_for_update())
                if run:
                    run.status = "FAILED"
                    run.error_code = "lease_expired_max_attempts"
                    run.completed_at = now
            candidates = session.scalars(select(MessageJob).where(
                MessageJob.attempt_count < func.least(MessageJob.max_attempts, self.settings.worker_max_attempts),
                or_(
                    and_(MessageJob.status == "QUEUED", MessageJob.available_at <= now),
                    and_(MessageJob.status == "RUNNING", MessageJob.lease_expires_at <= now),
                ),
            ).order_by(MessageJob.available_at, MessageJob.created_at, MessageJob.id)
             .with_for_update(skip_locked=True).limit(20)).all()
            job = None
            for candidate in candidates:
                conversation = session.scalar(select(Conversation.id).where(
                    Conversation.id == candidate.conversation_id,
                    Conversation.tenant_id == candidate.tenant_id,
                ).with_for_update())
                if conversation is None:
                    continue
                active = session.scalar(select(MessageJob.id).where(
                    MessageJob.tenant_id == candidate.tenant_id,
                    MessageJob.conversation_id == candidate.conversation_id,
                    MessageJob.status == "RUNNING",
                    MessageJob.id != candidate.id,
                ).limit(1))
                if active is not None:
                    continue
                job = candidate
                break
            if job is None:
                session.commit()
                return None
            token = uuid4()
            job.status = "RUNNING"
            job.attempt_count += 1
            job.lease_owner = self.worker_id
            job.lease_token = token
            job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
            job.heartbeat_at = now
            job.last_error_code = None
            lease = Lease(job.tenant_id, job.id, token)
            session.commit()
            return lease

    def heartbeat(self, lease: Lease) -> bool:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            result = session.execute(update(MessageJob).where(
                MessageJob.id == lease.item_id, MessageJob.tenant_id == lease.tenant_id,
                MessageJob.status == "RUNNING", MessageJob.lease_token == lease.token,
            ).values(heartbeat_at=now,
                     lease_expires_at=now + timedelta(seconds=self.settings.worker_lease_seconds)))
            session.commit()
            return result.rowcount == 1

    def process(self, lease: Lease) -> None:
        lost = threading.Event()
        stop = threading.Event()

        def keep_lease():
            while not stop.wait(self.settings.worker_heartbeat_seconds):
                try:
                    if not self.heartbeat(lease):
                        lost.set()
                        return
                except Exception:
                    logger.warning("worker lease heartbeat failed")
                    lost.set()
                    return

        heartbeat_thread = threading.Thread(target=keep_lease, daemon=True)
        heartbeat_thread.start()
        started = time.monotonic()
        try:
            with Session(self.engine, expire_on_commit=False) as session:
                job = session.scalar(select(MessageJob).where(
                    MessageJob.id == lease.item_id, MessageJob.tenant_id == lease.tenant_id,
                    MessageJob.status == "RUNNING", MessageJob.lease_token == lease.token,
                    MessageJob.lease_expires_at > datetime.now(timezone.utc),
                ).with_for_update())
                if job is None:
                    return
                message = session.scalar(select(Message).where(
                    Message.id == job.message_id, Message.tenant_id == job.tenant_id,
                ))
                conversation = session.scalar(select(Conversation).where(
                    Conversation.id == job.conversation_id, Conversation.tenant_id == job.tenant_id,
                ).with_for_update())
                if message is None or conversation is None:
                    raise RuntimeError("job_subject_missing")
                run = session.scalar(select(AgentRun).where(
                    AgentRun.tenant_id == job.tenant_id, AgentRun.message_id == message.id,
                ).with_for_update())
                if run and run.status == "COMPLETED":
                    # Recover the finalization gap after publication without re-running the model.
                    run.lease_token = lease.token
                    self._complete_job(session, job, lease)
                    return
                if run is None:
                    run = AgentRun(
                        tenant_id=job.tenant_id, job_id=job.id, conversation_id=conversation.id,
                        message_id=message.id, thread_id=str(conversation.id), lease_token=lease.token,
                        provider="openai-compatible", model=self.settings.llm_model,
                    )
                    session.add(run)
                    session.flush()
                else:
                    run.status = "RUNNING"
                    run.lease_token = lease.token
                    run.provider = "openai-compatible"
                    run.model = self.settings.llm_model
                    run.error_code = None
                    run.completed_at = None
                ConversationService.record_agent_progress(session, job.tenant_id, conversation.id,
                                                           run.id, lease.token, "worker_started")
                run_id = run.id
                related_case_id = message.related_case_id
                current_text = "\n".join(part.get("text", "") for part in message.content if part.get("type") == "text")
                context = AgentContextBuilder(session, job.tenant_id).build(conversation.id, message.id)
                if run.result_text:
                    stored_result = run.result_text
                    stored_payload = run.result_payload
                    stats = {"step_count": run.step_count, "input_tokens": run.input_tokens,
                             "output_tokens": run.output_tokens}
                else:
                    stored_result = None
                    stored_payload = None
                    stats = {}
                tenant_id, conversation_id, message_id = job.tenant_id, conversation.id, message.id
                session.commit()

            if lost.is_set():
                raise RuntimeError("worker_lease_lost")
            if stored_result is None:
                result, stats = self.runtime.invoke(
                    tenant_id=tenant_id, conversation_id=conversation_id, run_id=run_id,
                    lease_token=lease.token,
                    message_id=message_id, context=context, current_text=current_text,
                )
                if lost.is_set():
                    raise RuntimeError("worker_lease_lost")
                if isinstance(result, str):  # Existing local test adapters return text only.
                    result = AgentResult(result)
                if not isinstance(result, AgentResult):
                    raise RuntimeError("agent_result_invalid")
                with Session(self.engine) as session:
                    active_job = session.scalar(select(MessageJob).where(
                        MessageJob.id == lease.item_id, MessageJob.tenant_id == tenant_id,
                        MessageJob.status == "RUNNING", MessageJob.lease_token == lease.token,
                        MessageJob.lease_expires_at > datetime.now(timezone.utc),
                    ).with_for_update())
                    if active_job is None:
                        raise RuntimeError("worker_lease_lost")
                    run = session.scalar(select(AgentRun).where(
                        AgentRun.id == run_id, AgentRun.tenant_id == tenant_id,
                        AgentRun.lease_token == lease.token, AgentRun.status == "RUNNING",
                    ).with_for_update())
                    if run is None:
                        raise RuntimeError("agent_run_lease_lost")
                    proposals = session.scalars(select(AgentProposal).where(
                        AgentProposal.tenant_id == tenant_id,
                        AgentProposal.agent_run_id == run_id,
                        AgentProposal.conversation_id == conversation_id,
                        AgentProposal.proposal_type == "ACTION",
                        AgentProposal.visibility == "INTERNAL",
                    ).order_by(AgentProposal.id)).all()
                    stored_payload = {
                        **(run.result_payload or {}),
                        "schema_version": 1,
                        "ui_proposal": result.ui_proposal,
                        "ui_fallback_code": result.ui_fallback_code,
                        "action_proposals": [str(proposal.id) for proposal in proposals],
                    }
                    run.result_text = result.text
                    run.result_payload = stored_payload
                    run.step_count = int(stats.get("step_count", 0))
                    run.input_tokens = stats.get("input_tokens")
                    run.output_tokens = stats.get("output_tokens")
                    run.duration_ms = int((time.monotonic() - started) * 1000)
                    session.commit()
                stored_result = result.text

            if lost.is_set():
                raise RuntimeError("worker_lease_lost")
            with Session(self.engine, expire_on_commit=False) as session:
                active_job = session.scalar(select(MessageJob).where(
                    MessageJob.id == lease.item_id, MessageJob.tenant_id == lease.tenant_id,
                    MessageJob.status == "RUNNING", MessageJob.lease_token == lease.token,
                    MessageJob.lease_expires_at > datetime.now(timezone.utc),
                ).with_for_update())
                if active_job is None:
                    raise RuntimeError("worker_lease_lost")
                service = ConversationService(session, actor=None)
                service.publish_agent_response(
                    tenant_id=tenant_id, conversation_id=conversation_id, agent_run_id=run_id,
                    lease_token=lease.token, text=stored_result, related_case_id=related_case_id,
                )
                job = session.scalar(select(MessageJob).where(
                    MessageJob.id == lease.item_id, MessageJob.tenant_id == lease.tenant_id,
                    MessageJob.lease_token == lease.token,
                ).with_for_update())
                if job is None:
                    raise RuntimeError("worker_lease_lost")
                self._complete_job(session, job, lease)
        except Exception as error:
            self._fail(lease, self._error_code(error))
        finally:
            stop.set()
            heartbeat_thread.join(timeout=1)

    def _complete_job(self, session: Session, job: MessageJob, lease: Lease):
        if job.lease_token != lease.token:
            raise RuntimeError("worker_lease_lost")
        run = session.scalar(select(AgentRun).where(
            AgentRun.tenant_id == lease.tenant_id, AgentRun.job_id == job.id,
            AgentRun.conversation_id == job.conversation_id,
        ))
        if run is None:
            raise RuntimeError("agent_run_unavailable")
        ConversationService.record_agent_progress(session, job.tenant_id, job.conversation_id,
                                                   run.id, lease.token, "worker_completed")
        job.status = "COMPLETED"
        job.completed_at = datetime.now(timezone.utc)
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.last_error_code = None
        session.commit()

    def _fail(self, lease: Lease, error_code: str):
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            job = session.scalar(select(MessageJob).where(
                MessageJob.id == lease.item_id, MessageJob.tenant_id == lease.tenant_id,
                MessageJob.status == "RUNNING", MessageJob.lease_token == lease.token,
                MessageJob.lease_expires_at > now,
            ).with_for_update())
            if job is None:
                return
            terminal = job.attempt_count >= min(job.max_attempts, self.settings.worker_max_attempts)
            session.scalar(select(Conversation).where(
                Conversation.id == job.conversation_id, Conversation.tenant_id == job.tenant_id,
            ).with_for_update())
            run = session.scalar(select(AgentRun).where(
                AgentRun.tenant_id == lease.tenant_id, AgentRun.job_id == job.id,
                AgentRun.lease_token == lease.token,
            ).with_for_update())
            if run and run.status != "COMPLETED":
                run.status = "FAILED"
                run.error_code = error_code
                run.completed_at = now
                try:
                    ConversationService.record_agent_progress(session, job.tenant_id, job.conversation_id,
                                                               run.id, lease.token, "worker_failed")
                except ValueError:
                    # A withdrawn conversation/source authorization cannot emit progress.
                    pass
            job.status = "FAILED" if terminal else "QUEUED"
            job.last_error_code = error_code
            job.available_at = now + timedelta(seconds=min(300, 2 ** job.attempt_count))
            job.lease_owner = None
            job.lease_token = None
            job.lease_expires_at = None
            session.commit()
        logger.warning("message job ended: status=%s error_code=%s", "FAILED" if terminal else "QUEUED", error_code)

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, ServiceError):
            return "conversation_policy_rejected"
        if str(error) in {"worker_lease_lost", "agent_run_lease_lost"}:
            return "lease_lost"
        return "agent_execution_failed"

    def run_once(self) -> bool:
        if not self.runtime.configured:
            raise RuntimeError("Configure SERVICEOS_LLM_MODEL, SERVICEOS_LLM_BASE_URL and SERVICEOS_LLM_API_KEY before starting the Worker.")
        lease = self.claim_one()
        if lease is None:
            return False
        self.process(lease)
        return True


class OutboxDispatcher:
    def __init__(self, engine, lease_seconds: int = 30, worker_id: str | None = None):
        self.engine = engine
        self.lease_seconds = lease_seconds
        self.worker_id = worker_id or f"outbox-{uuid4()}"

    def claim_batch(self, limit: int = 50) -> list[Lease]:
        now = datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session:
            session.execute(update(OutboxEvent).where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.dead_lettered_at.is_(None),
                OutboxEvent.conversation_id.is_not(None),
                OutboxEvent.attempt_count >= OutboxEvent.max_attempts,
                or_(OutboxEvent.lease_expires_at.is_(None), OutboxEvent.lease_expires_at <= now),
            ).values(dead_lettered_at=now, lease_owner=None, lease_token=None,
                     lease_expires_at=None, last_error_code="lease_expired_max_attempts"))
            rows = session.scalars(select(OutboxEvent).where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.dead_lettered_at.is_(None),
                OutboxEvent.conversation_id.is_not(None),
                OutboxEvent.attempt_count < OutboxEvent.max_attempts,
                OutboxEvent.available_at <= now,
                or_(OutboxEvent.lease_expires_at.is_(None), OutboxEvent.lease_expires_at <= now),
            ).order_by(OutboxEvent.created_at, OutboxEvent.id)
             .with_for_update(skip_locked=True).limit(limit)).all()
            leases = []
            for row in rows:
                token = uuid4()
                row.attempt_count += 1
                row.lease_owner = self.worker_id
                row.lease_token = token
                row.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
                row.heartbeat_at = now
                leases.append(Lease(row.tenant_id, row.id, token))
            session.commit()
            return leases

    def dispatch(self, lease: Lease) -> bool:
        with Session(self.engine, expire_on_commit=False) as session:
            event = session.scalar(select(OutboxEvent).where(
                OutboxEvent.id == lease.item_id, OutboxEvent.tenant_id == lease.tenant_id,
                OutboxEvent.lease_token == lease.token, OutboxEvent.published_at.is_(None),
            ).with_for_update())
            if event is None:
                return False
            try:
                if event.conversation_id is None:
                    return False
                ConversationService.dispatch_outbox_event(session, event)
                event.published_at = datetime.now(timezone.utc)
                event.lease_owner = None
                event.lease_token = None
                event.lease_expires_at = None
                event.last_error_code = None
                session.commit()
                return True
            except Exception:
                session.rollback()
                self._fail(lease, "outbox_dispatch_failed")
                return False

    def _fail(self, lease: Lease, error_code: str):
        with Session(self.engine) as session:
            event = session.scalar(select(OutboxEvent).where(
                OutboxEvent.id == lease.item_id, OutboxEvent.tenant_id == lease.tenant_id,
                OutboxEvent.lease_token == lease.token,
            ).with_for_update())
            if event is None:
                return
            event.last_error_code = error_code
            if event.attempt_count >= event.max_attempts:
                event.dead_lettered_at = datetime.now(timezone.utc)
            event.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** event.attempt_count))
            event.lease_owner = None
            event.lease_token = None
            event.lease_expires_at = None
            session.commit()

    def dispatch_batch(self, limit: int = 50) -> int:
        return sum(1 for lease in self.claim_batch(limit) if self.dispatch(lease))


def run_worker_forever(settings: Settings):
    if not settings.llm_configured:
        raise RuntimeError("LLM provider is not configured; no message jobs were claimed.")
    from serviceos_api.worker.actions import MockActionWorker
    from serviceos_api.worker.health import run_loop
    from serviceos_api.worker.inspection import EvidenceInspectionWorker

    engine = build_engine()
    messages = MessageWorker(engine, settings)
    evidence = EvidenceInspectionWorker(engine, settings) if settings.environment in ("development", "test") else None
    actions = MockActionWorker(engine, settings) if settings.environment in ("development", "test") else None
    outbox = OutboxDispatcher(engine, settings.worker_lease_seconds)

    def poll() -> bool:
        did_work = messages.run_once()
        did_work = (evidence.run_once() if evidence is not None else False) or did_work
        did_work = (actions.run_once() if actions is not None else False) or did_work
        return bool(outbox.dispatch_batch()) or did_work

    try:
        # run_loop writes the heartbeat that the container healthcheck reads.
        run_loop(ROLE, poll)
    finally:
        engine.dispose()
