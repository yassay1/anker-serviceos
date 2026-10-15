import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import Business, ConversationBusiness, get_actor, get_session, local_login_allowed
from serviceos_api.application import auth
from serviceos_api.application.services import ConversationService
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.contracts import (
    ActorRead, AttachConversation, AttachDevice, CandidateFact, CaseRead, ConversationList, ConversationRead, DeskCaseSummary,
    CreateCase, CreateConversation, CreateDevice, DeviceRead, FactDecision, FactRead, LocalLogin, MessagePage,
    MessageReceipt, SendMessage, TransitionCase, UpdateCase, UpdateDevice, ModeTransition, AssistanceRequest,
    ClaimTask, TaskRead, ProposalRead, ProposalDecision, EventPage, UIDocumentRead,
    UIActionRequest, UIActionResult, ArchiveCaseFact,
)
from serviceos_api.persistence.models import Conversation, DevicePassport, ServiceCase

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("serviceos.events")


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
    return ConversationList(items=[ConversationRead.model_validate(row) for row in service.list_resources(Conversation, limit)])


@router.get("/conversations/{id}", response_model=ConversationRead, tags=["conversations"], operation_id="read_conversation")
def read_conversation(id: UUID, service: Business):
    return ConversationRead.model_validate(service.resource(Conversation, id))


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
    return ConversationRead.model_validate(service.transition_mode(id, body))


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
    with Session(engine) as session:
        ConversationService(session, actor).events(id, after=0, limit=1)
    cursor = max(after, last_event_id or 0)
    token = request.cookies.get(auth.COOKIE_NAME)

    async def generate():
        nonlocal cursor
        while not await request.is_disconnected():
            with Session(engine) as session:
                try:
                    current_actor = auth.authenticated_principal(session, token)
                    page = ConversationService(session, current_actor).events(id, cursor, 100)
                except ServiceError:
                    return
                except Exception as error:
                    logger.error("", extra={
                        "event_code": "events.stream_failed", "error_code": "event_stream_failed",
                        "exception_type": type(error).__name__,
                    })
                    return
                for event in page.items:
                    yield f"id: {event.sequence}\ndata: {event.model_dump_json()}\n\n"
                cursor = page.next_after
            if not page.items:
                yield ": keepalive\n\n"
                await asyncio.sleep(2)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/cases", response_model=CaseRead, status_code=201, tags=["cases"], operation_id="create_case")
def create_case(body: CreateCase, service: Business):
    return CaseRead.model_validate(service.create(ServiceCase, body))


@router.get("/cases", response_model=list[CaseRead], tags=["cases"], operation_id="list_cases")
def list_cases(service: Business):
    return [CaseRead.model_validate(row) for row in service.list_resources(ServiceCase)]


@router.get("/cases/{id}", response_model=CaseRead, tags=["cases"], operation_id="read_case")
def read_case(id: UUID, service: Business):
    return CaseRead.model_validate(service.resource(ServiceCase, id))


@router.patch("/cases/{id}", response_model=CaseRead, tags=["cases"], operation_id="update_case")
def update_case(id: UUID, body: UpdateCase, service: Business):
    return CaseRead.model_validate(service.update_case(id, body))


@router.post("/cases/{id}/transitions", response_model=CaseRead, tags=["cases"], operation_id="transition_case")
def transition_case(id: UUID, body: TransitionCase, service: Business):
    return CaseRead.model_validate(service.transition_case(id, body))


@router.delete("/cases/{id}", status_code=204, tags=["cases"], operation_id="archive_case")
def archive_case(id: UUID, service: Business):
    service.archive(ServiceCase, id)
    return Response(status_code=204)


@router.post("/cases/{id}/devices", response_model=CaseRead, tags=["cases"], operation_id="attach_device")
def attach_device(id: UUID, body: AttachDevice, service: Business):
    return CaseRead.model_validate(service.attach(id, body, DevicePassport))


@router.post("/cases/{id}/conversations", response_model=CaseRead, tags=["cases"], operation_id="attach_conversation")
def attach_conversation(id: UUID, body: AttachConversation, service: Business):
    return CaseRead.model_validate(service.attach(id, body, Conversation))


@router.post("/devices", response_model=DeviceRead, status_code=201, tags=["devices"], operation_id="create_device")
def create_device(body: CreateDevice, service: Business):
    return service.device_read(service.create(DevicePassport, body))


@router.get("/devices", response_model=list[DeviceRead], tags=["devices"], operation_id="list_devices")
def list_devices(service: Business):
    return [service.device_read(row) for row in service.list_resources(DevicePassport)]


@router.get("/devices/{id}", response_model=DeviceRead, tags=["devices"], operation_id="read_device")
def read_device(id: UUID, service: Business):
    return service.device_read(service.resource(DevicePassport, id))


@router.patch("/devices/{id}", response_model=DeviceRead, tags=["devices"], operation_id="update_device")
def update_device(id: UUID, body: UpdateDevice, service: Business):
    return service.device_read(service.update_device(id, body))


@router.delete("/devices/{id}", status_code=204, tags=["devices"], operation_id="archive_device")
def archive_device(id: UUID, service: Business):
    service.archive(DevicePassport, id)
    return Response(status_code=204)


@router.get("/devices/{id}/cases", response_model=list[CaseRead], tags=["devices"], operation_id="device_cases")
def device_cases(id: UUID, service: Business):
    return [CaseRead.model_validate(row) for row in service.device_cases(id)]


@router.post("/devices/{id}/facts", response_model=FactRead, status_code=201, tags=["devices"], operation_id="create_candidate_fact")
def create_candidate_fact(id: UUID, body: CandidateFact, service: Business):
    return FactRead.model_validate(service.create_candidate_fact(id, body))


@router.get("/devices/{id}/fact-candidates", response_model=list[FactRead], tags=["devices"], operation_id="list_candidate_facts")
def list_candidate_facts(id: UUID, service: Business):
    return [FactRead.model_validate(row) for row in service.candidate_facts(id)]


@router.get("/devices/{id}/fact-review", response_model=list[FactRead], tags=["devices"],
            operation_id="list_case_fact_review")
def list_case_fact_review(id: UUID, service: Business):
    return [FactRead.model_validate(row) for row in service.case_fact_review(id)]


@router.post("/devices/{id}/facts/{fact_id}/verify", response_model=FactRead, tags=["devices"], operation_id="verify_fact")
def verify_fact(id: UUID, fact_id: UUID, body: FactDecision, service: Business):
    return FactRead.model_validate(service.decide_fact(id, fact_id, body))


@router.post("/devices/{id}/facts/{fact_id}/retract", response_model=FactRead, tags=["devices"], operation_id="retract_fact")
def retract_fact(id: UUID, fact_id: UUID, body: FactDecision, service: Business):
    return FactRead.model_validate(service.decide_fact(id, fact_id, body, retract=True))


@router.post("/cases/{case_id}/devices/{device_id}/facts/{fact_id}/archive", response_model=FactRead,
             tags=["devices"], operation_id="archive_case_device_fact")
def archive_case_device_fact(case_id: UUID, device_id: UUID, fact_id: UUID,
                             body: ArchiveCaseFact, service: Business):
    return FactRead.model_validate(service.archive_case_fact(case_id, device_id, fact_id, body))
