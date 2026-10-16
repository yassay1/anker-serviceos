import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import Business, ConversationBusiness, get_actor, get_session, local_login_allowed
from serviceos_api.application import auth
from serviceos_api.application.conversation_titles import conversation_reads
from serviceos_api.application.services import ConversationService
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.contracts import (
    ActorRead, ConversationList, ConversationRead, DeskCaseSummary, CreateConversation, LocalLogin, MessagePage,
    MessageReceipt, SendMessage, ModeTransition, AssistanceRequest, ClaimTask, TaskRead, ProposalRead,
    ProposalDecision, EventPage, UIDocumentRead, UIActionRequest, UIActionResult,
)
from serviceos_api.persistence.models import Conversation

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("serviceos.events")
_stream_counter_lock = threading.Lock()
_active_streams = 0


def _change_active_streams(delta: int) -> int:
    global _active_streams
    with _stream_counter_lock:
        _active_streams = max(0, _active_streams + delta)
        return _active_streams


def _check_stream_access(engine, actor, conversation_id: UUID):
    with Session(engine) as session:
        ConversationService(session, actor).events(conversation_id, after=0, limit=1)


def _read_authorized_event_page(engine, conversation_id: UUID, token: str | None, cursor: int):
    started = time.perf_counter()
    with Session(engine) as session:
        actor = auth.authenticated_principal(session, token)
        page = ConversationService(session, actor).events(conversation_id, cursor, 100)
    return page, round((time.perf_counter() - started) * 1000, 2)


@router.post("/local-auth/login", response_model=ActorRead, tags=["local-auth"],
             dependencies=[Depends(local_login_allowed)], operation_id="login_local")
def login(body: LocalLogin, request: Request, response: Response, session: Session = Depends(get_session)):
    actor, token = auth.login_local(session, request.app.state.settings, body.username, body.password.get_secret_value())
    response.set_cookie(auth.COOKIE_NAME, token, max_age=auth.SESSION_SECONDS, httponly=True, samesite="strict", secure=False)
    response.headers["Cache-Control"] = "no-store"
    return ActorRead.model_validate(actor)


@router.get("/auth/me", response_model=ActorRead, tags=["auth"], operation_id="read_actor")
def me(response: Response, actor=Depends(get_actor)):
    response.headers["Cache-Control"] = "no-store"
    return ActorRead.model_validate(actor)


@router.post("/auth/logout", status_code=204, tags=["auth"], operation_id="logout")
def logout(request: Request, actor=Depends(get_actor), session: Session = Depends(get_session)):
    auth.logout(session, request.cookies.get(auth.COOKIE_NAME, ""))
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


@router.post("/conversations", response_model=ConversationRead, status_code=201, tags=["conversations"], operation_id="create_conversation")
def create_conversation(body: CreateConversation, service: Business):
    return ConversationRead.model_validate(service.create(Conversation, body))


@router.get("/conversations", response_model=ConversationList, tags=["conversations"], operation_id="list_conversations")
def list_conversations(service: Business, limit: int = Query(default=50, ge=1, le=100)):
    return ConversationList(items=conversation_reads(service.session, service.actor.tenant_id,
                                                     service.list_resources(Conversation, limit)))


@router.get("/conversations/{id}", response_model=ConversationRead, tags=["conversations"], operation_id="read_conversation")
def read_conversation(id: UUID, service: Business):
    return conversation_reads(service.session, service.actor.tenant_id, [service.resource(Conversation, id)])[0]


@router.post("/conversations/{id}/messages", response_model=MessageReceipt, status_code=status.HTTP_202_ACCEPTED,
             tags=["messages"], operation_id="send_message")
def send_message(id: UUID, body: SendMessage, service: ConversationBusiness):
    return service.send_message(id, body)


@router.get("/conversations/{id}/messages", response_model=MessagePage, tags=["messages"], operation_id="list_messages")
def list_messages(id: UUID, service: ConversationBusiness, cursor: UUID | None = None, limit: int = Query(default=50, ge=1, le=100)):
    return service.messages(id, cursor, limit)


@router.get("/conversations/{id}/case-summaries", response_model=list[DeskCaseSummary],
            tags=["cases"], operation_id="list_desk_case_summaries")
def list_desk_case_summaries(id: UUID, service: ConversationBusiness):
    return service.desk_case_summaries(id)


@router.post("/conversations/{id}/mode-transitions", response_model=ConversationRead,
             tags=["collaboration"], operation_id="transition_mode")
def transition_mode(id: UUID, body: ModeTransition, service: ConversationBusiness):
    return conversation_reads(service.session, service.actor.tenant_id, [service.transition_mode(id, body)])[0]


@router.post("/conversations/{id}/assistance-requests", response_model=TaskRead, status_code=201,
             tags=["collaboration"], operation_id="request_assistance")
def request_assistance(id: UUID, body: AssistanceRequest, service: ConversationBusiness):
    return service.request_assistance(id, body)


@router.get("/conversations/{id}/tasks", response_model=list[TaskRead],
            tags=["collaboration"], operation_id="list_tasks")
def list_tasks(id: UUID, service: ConversationBusiness):
    return service.tasks(id)


@router.post("/tasks/{id}/claim", response_model=TaskRead,
             tags=["collaboration"], operation_id="claim_task")
def claim_task(id: UUID, body: ClaimTask, service: ConversationBusiness):
    return service.claim_task(id, body)


@router.get("/conversations/{id}/proposals", response_model=list[ProposalRead],
            tags=["collaboration"], operation_id="list_proposals")
def list_proposals(id: UUID, service: ConversationBusiness):
    return service.proposals(id)


@router.post("/proposals/{id}/decision", response_model=ProposalRead,
             tags=["collaboration"], operation_id="decide_proposal")
def decide_proposal(id: UUID, body: ProposalDecision, service: ConversationBusiness):
    return service.decide_proposal(id, body)


@router.get("/conversations/{id}/event-history", response_model=EventPage,
            tags=["events"], operation_id="list_event_history")
def list_event_history(id: UUID, service: ConversationBusiness,
                       after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100)):
    return service.events(id, after, limit)


@router.get("/conversations/{id}/ui-document", response_model=UIDocumentRead | None,
            tags=["ui"], operation_id="read_ui_document")
def read_ui_document(id: UUID, service: ConversationBusiness):
    return service.current_ui(id)


@router.post("/conversations/{id}/ui-document/refresh", response_model=UIDocumentRead,
             tags=["ui"], operation_id="refresh_ui_document")
def refresh_ui_document(id: UUID, service: ConversationBusiness):
    return service.publish_ui_projection(id)


@router.post("/conversations/{id}/ui-actions", response_model=UIActionResult,
             tags=["ui"], operation_id="invoke_ui_action")
def invoke_ui_action(id: UUID, body: UIActionRequest, service: ConversationBusiness):
    return service.invoke_ui_action(id, body)


@router.get("/conversations/{id}/events", tags=["events"], operation_id="stream_events")
async def stream_events(id: UUID, request: Request, actor=Depends(get_actor),
                        after: int = Query(default=0, ge=0),
                        last_event_id: int | None = Header(default=None, alias="Last-Event-ID", ge=0)):
    engine = request.app.state.database_engine
    await run_in_threadpool(_check_stream_access, engine, actor, id)
    cursor = max(after, last_event_id or 0)
    token = request.cookies.get(auth.COOKIE_NAME)

    async def generate():
        nonlocal cursor
        started = time.perf_counter()
        active = _change_active_streams(1)
        logger.info("", extra={
            "event_code": "events.stream_opened", "active_connections": active,
        })
        poll_count = empty_poll_count = event_count = total_query_ms = max_event_age_ms = 0
        close_reason = "disconnected"
        try:
            while not await request.is_disconnected():
                try:
                    page, query_ms = await run_in_threadpool(
                        _read_authorized_event_page, engine, id, token, cursor)
                except ServiceError:
                    close_reason = "authorization_revoked"
                    return
                except Exception as error:
                    close_reason = "read_error"
                    logger.error("", extra={
                        "event_code": "events.stream_failed", "error_code": "event_stream_failed",
                        "exception_type": type(error).__name__,
                    })
                    return
                poll_count += 1
                total_query_ms += round(query_ms)
                event_count += len(page.items)
                if not page.items:
                    empty_poll_count += 1
                for event in page.items:
                    age_ms = max(0, round((datetime.now(timezone.utc) - event.created_at).total_seconds() * 1000))
                    max_event_age_ms = max(max_event_age_ms, age_ms)
                    yield f"id: {event.sequence}\ndata: {event.model_dump_json()}\n\n"
                cursor = page.next_after
                if not page.items:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(2)
        finally:
            active = _change_active_streams(-1)
            logger.info("", extra={
                "event_code": "events.stream_closed", "active_connections": active,
                "poll_count": poll_count, "empty_poll_count": empty_poll_count,
                "event_count": event_count, "total_query_ms": total_query_ms,
                "max_event_age_ms": max_event_age_ms,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "close_reason": close_reason,
            })

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
