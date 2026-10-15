"""Case and Device HTTP routes; application services own their business rules."""

from uuid import UUID

from fastapi import APIRouter, Response, status

from serviceos_api.api.dependencies import Business
from serviceos_api.application.contracts import (
    ArchiveCaseFact, AttachConversation, AttachDevice, CandidateFact, CaseRead, CreateCase, CreateDevice,
    DeviceRead, FactDecision, FactRead, TransitionCase, UpdateCase, UpdateDevice,
)
from serviceos_api.persistence.models import Conversation, DevicePassport, ServiceCase

router = APIRouter(prefix="/api/v1")


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
