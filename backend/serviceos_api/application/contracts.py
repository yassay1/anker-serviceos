"""Typed application commands and results, also used as the HTTP contract."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LocalLogin(Schema):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr


class ActorRead(Schema):
    tenant_id: UUID
    actor_id: UUID
    kind: Literal["CUSTOMER", "STAFF"]
    display_name: str
    role: str | None = None


class CreateConversation(Schema):
    customer_id: UUID | None = None


class ConversationRead(Schema):
    id: UUID
    customer_id: UUID
    status: str
    collaboration_mode: str
    reply_policy: str
    version: int
    created_at: datetime


class ConversationList(Schema):
    items: list[ConversationRead]


class ModeTransition(Schema):
    target_mode: Literal["AI_LEAD", "CO_SERVICE", "HUMAN_LEAD"]
    reply_policy: Literal["AI_AUTO", "AI_REVIEW_REQUIRED", "HUMAN_ONLY"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class AssistanceRequest(Schema):
    reason: str = Field(min_length=3, max_length=1000)
    case_id: UUID | None = None


class ClaimTask(Schema):
    expected_version: int = Field(ge=1)


class TaskRead(Schema):
    id: UUID
    conversation_id: UUID
    case_id: UUID | None
    reason: str
    status: str
    version: int
    assignee_id: UUID | None = None
    created_at: datetime


class ProposalRead(Schema):
    id: UUID
    conversation_id: UUID
    proposal_type: str
    payload: dict[str, Any]
    status: str
    created_at: datetime


class ProposalDecision(Schema):
    decision_id: UUID
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=3, max_length=1000)


class CreateCase(Schema):
    customer_id: UUID | None = None
    problem_text: str = Field(min_length=1, max_length=8000)
    user_goal: str | None = Field(default=None, max_length=2000)


class UpdateCase(Schema):
    expected_version: int = Field(ge=1)
    problem_text: str | None = Field(default=None, min_length=1, max_length=8000)
    user_goal: str | None = Field(default=None, max_length=2000)


class TransitionCase(Schema):
    expected_version: int = Field(ge=1)
    target_status: Literal["IN_PROGRESS", "WAITING_CUSTOMER", "WAITING_EXTERNAL", "RESOLVED", "CLOSED"]
    reason: str = Field(min_length=3, max_length=1000)


class CaseRead(Schema):
    id: UUID
    customer_id: UUID
    problem_text: str
    user_goal: str | None
    status: str
    version: int
    created_at: datetime


class SummaryFact(Schema):
    label: str
    value: str
    source: str
    verification: Literal["UNVERIFIED", "CANDIDATE", "VERIFIED", "RETRACTED"]


class DeskCaseSummary(Schema):
    case: CaseRead
    facts: list[SummaryFact]
    device_ids: list[UUID]


class CreateDevice(Schema):
    customer_id: UUID | None = None
    model: str | None = Field(default=None, min_length=1, max_length=160)
    serial_number: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def has_identity(self):
        if not (self.model and self.model.strip()) and not (self.serial_number and self.serial_number.strip()):
            raise ValueError("提供型号或设备标识；身份未知时可以先创建案例。")
        return self


class UpdateDevice(Schema):
    expected_revision: int = Field(ge=1)
    model: str | None = Field(default=None, min_length=1, max_length=160)
    serial_number: str | None = Field(default=None, min_length=1, max_length=160)


class DeviceRead(Schema):
    id: UUID
    customer_id: UUID
    model: str | None
    serial_number: str | None
    identity_status: str
    revision: int
    created_at: datetime
    verified_facts: list["VerifiedDeviceFact"] = Field(default_factory=list)


class VerifiedDeviceFact(Schema):
    id: UUID
    fact_key: str
    value: Any
    source: str
    verified_by: str
    verified_at: datetime


class CandidateFact(Schema):
    expected_device_revision: int = Field(ge=1)
    fact_key: str = Field(min_length=2, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")
    value: Any


class FactDecision(Schema):
    expected_device_revision: int = Field(ge=1)
    expected_fact_revision: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class FactRead(Schema):
    id: UUID
    device_id: UUID
    fact_key: str
    value: Any
    source_kind: str
    source: str
    validity: str
    revision: int
    verified_by: str | None
    verified_at: datetime | None
    retracted_at: datetime | None
    retraction_reason: str | None


class AttachDevice(Schema):
    device_id: UUID
    expected_version: int = Field(ge=1)
    role: str = Field(default="AFFECTED", min_length=1, max_length=32)
    is_primary: bool = False


class AttachConversation(Schema):
    conversation_id: UUID
    expected_version: int = Field(ge=1)


class TextPart(Schema):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def not_blank(self):
        if not self.text.strip():
            raise ValueError("消息不能为空。")
        return self


class SendMessage(Schema):
    client_message_id: UUID
    content: list[TextPart] = Field(min_length=1, max_length=10)
    related_case_id: UUID | None = None
    visibility: Literal["PUBLIC", "INTERNAL"] = "PUBLIC"


class MessageRead(Schema):
    id: UUID
    conversation_id: UUID
    author_kind: str
    visibility: str
    content: list[TextPart]
    client_message_id: UUID | None
    related_case_id: UUID | None
    created_at: datetime


class MessagePage(Schema):
    items: list[MessageRead]
    next_cursor: UUID | None = None


class MessageReceipt(Schema):
    message: MessageRead
    replayed: bool
    processing_state: Literal["QUEUED", "NOT_SCHEDULED"]


class EventRead(Schema):
    id: UUID
    conversation_id: UUID
    sequence: int
    type: str
    visibility: Literal["PUBLIC", "INTERNAL"]
    data: dict[str, Any]
    created_at: datetime


class EventPage(Schema):
    items: list[EventRead]
    next_after: int


class UIDataSource(Schema):
    kind: Literal["CONVERSATION_VIEW", "CASE_VIEW", "TASK_VIEW", "AGENT_RUN_VIEW"]
    resource_id: UUID
    resource_version: int = Field(ge=1)
    binding: str


class UIAction(Schema):
    action_id: str
    intent: Literal["REQUEST_ASSISTANCE"]
    input_schema_ref: str


class UIComponent(Schema):
    id: str
    type: str
    props: dict[str, str]
    data_source: UIDataSource
    actions: list[UIAction]
    children: list[str]


class UIDocumentRead(Schema):
    ui_id: UUID
    revision: int
    schema_version: int
    catalog_version: int
    surface: str
    audience: Literal["CUSTOMER", "STAFF"]
    visibility: Literal["PUBLIC", "INTERNAL"]
    source_agent_run_id: UUID | None
    components: list[UIComponent]
    fallback_text: str
    status: str
    created_at: datetime
    expires_at: datetime | None


class UIActionRequest(Schema):
    client_action_id: UUID
    ui_id: UUID
    revision: int = Field(ge=1)
    action_id: Literal["request-human-assistance"]
    input: dict[str, Any]
    expected_conversation_version: int = Field(ge=1)


class UIActionResult(Schema):
    client_action_id: UUID
    status: Literal["ACCEPTED"]
    task_id: UUID
    replayed: bool


class ServiceErrorBody(Schema):
    code: str | None = None
    detail: str
    current_version: int | None = None


class UploadEvidence(Schema):
    client_evidence_id: UUID
    expected_case_version: int = Field(ge=1)
    visibility: Literal["PUBLIC", "INTERNAL"] = "PUBLIC"


class EvidenceRead(Schema):
    id: UUID
    case_id: UUID
    client_evidence_id: UUID
    visibility: Literal["PUBLIC", "INTERNAL"]
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(ge=1, le=10 * 1024 * 1024)
    inspection_status: Literal["PENDING", "CLEAN", "REJECTED"]
    verification: Literal["UNVERIFIED", "VERIFIED", "RETRACTED"]
    source_kind: Literal["CUSTOMER", "STAFF"]
    created_at: datetime


class EvidencePage(Schema):
    items: list[EvidenceRead]
    next_cursor: UUID | None = None


class MockActionRequest(Schema):
    client_action_id: UUID
    expected_case_version: int = Field(ge=1)
    action_kind: Literal["MOCK_SERVICE_REQUEST"]
    source_proposal_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)


class MockReceiptRead(Schema):
    adapter: Literal["MOCK"] = "MOCK"
    external_reference: str
    result: Literal["SUCCEEDED", "FAILED"]
    received_at: datetime


class CaseActionRead(Schema):
    id: UUID
    case_id: UUID
    action_kind: Literal["MOCK_SERVICE_REQUEST"]
    adapter: Literal["MOCK"]
    status: Literal["WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN", "SUCCEEDED", "FAILED", "REJECTED"]
    version: int
    approval_id: UUID | None = None
    receipt: MockReceiptRead | None = None
    reason: str | None = None
    requested_by: UUID | None = None
    created_at: datetime


class ActionApprovalDecision(Schema):
    decision_id: UUID
    expected_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=3, max_length=1000)


class ActionApprovalRead(Schema):
    id: UUID
    action_id: UUID
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    version: int
    decided_at: datetime | None


class ResolutionContractRead(Schema):
    id: UUID
    case_id: UUID
    action_id: UUID
    version: int
    conditions: list[str]
    created_at: datetime


class VerificationRequest(Schema):
    client_verification_id: UUID
    expected_case_version: int = Field(ge=1)
    expected_resolution_contract_version: int = Field(ge=1)
    observed_result: Literal["WORKING", "NOT_WORKING", "UNCERTAIN"]
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=10)
    note: str = Field(max_length=2000)


class VerificationRead(Schema):
    id: UUID
    case_id: UUID
    contract_id: UUID
    client_verification_id: UUID
    observed_result: Literal["WORKING", "NOT_WORKING", "UNCERTAIN"]
    decision: Literal["PENDING", "VERIFIED_RESOLVED", "NOT_RESOLVED"]
    note: str
    case_status: str
    created_at: datetime
