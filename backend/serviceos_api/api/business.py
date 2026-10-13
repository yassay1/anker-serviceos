from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import Business, ConversationBusiness, get_actor, get_session, local_login_allowed
from serviceos_api.application import auth
from serviceos_api.application.contracts import (
    ActorRead, AttachConversation, AttachDevice, CandidateFact, CaseRead, ConversationList, ConversationRead,
    CreateCase, CreateConversation, CreateDevice, DeviceRead, FactDecision, FactRead, LocalLogin, MessagePage,
    MessageReceipt, SendMessage, TransitionCase, UpdateCase, UpdateDevice,
)
from serviceos_api.persistence.models import Conversation, DevicePassport, ServiceCase

router = APIRouter(prefix="/api/v1")


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


@router.post("/devices/{id}/facts/{fact_id}/verify", response_model=FactRead, tags=["devices"], operation_id="verify_fact")
def verify_fact(id: UUID, fact_id: UUID, body: FactDecision, service: Business):
    return FactRead.model_validate(service.decide_fact(id, fact_id, body))


@router.post("/devices/{id}/facts/{fact_id}/retract", response_model=FactRead, tags=["devices"], operation_id="retract_fact")
def retract_fact(id: UUID, fact_id: UUID, body: FactDecision, service: Business):
    return FactRead.model_validate(service.decide_fact(id, fact_id, body, retract=True))
