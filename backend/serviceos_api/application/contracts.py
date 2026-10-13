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
