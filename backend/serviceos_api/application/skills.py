"""Fixed, versioned service methods; neither remote code nor business authority."""

from datetime import datetime
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import and_, case, cast, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import ConversationService
from serviceos_api.persistence.models import AgentRun, Conversation


class EmotionAssessment(BaseModel):
    """Prepared only. No producer, classifier, or authorized state transition exists."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    category: Literal["unknown", "neutral", "frustrated", "angry", "anxious", "confused", "satisfied"]
    intensity: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    uncertainty: str = Field(min_length=1, max_length=500)
    source_message_ids: list[UUID] = Field(min_length=1, max_length=8)
    recommended_strategy: Literal["neutral", "empathetic", "concise", "offer_human"]
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"

    @field_validator("uncertainty")
    @classmethod
    def nonblank_uncertainty(cls, value):
        if not value.strip():
            raise ValueError("uncertainty_required")
        return value


class SkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_message_ids: list[UUID] = Field(min_length=1, max_length=8)


class DiagnosisGuidance(BaseModel):
    """A future guidance result, not an assertion of diagnosis or resolution."""

    model_config = ConfigDict(extra="forbid", strict=True)
    source_message_ids: list[UUID] = Field(min_length=1, max_length=8)
    evidence_summary: str = Field(min_length=1, max_length=500)
    next_step: str = Field(min_length=1, max_length=500)
    failure_exit: str = Field(min_length=1, max_length=500)
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: str
    version: str
    title: str
    description: str
    availability: Literal["AVAILABLE", "PREPARED"]
    input_schema: dict
    output_schema: dict
    applicability: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_ui_components: tuple[str, ...]
    risk_level: Literal["LOW"]
    failure_exit: str


SKILL_REGISTRY = MappingProxyType({
    ("diagnose-no-charge", "1.0.0"): SkillDefinition(
        skill_id="diagnose-no-charge", version="1.0.0", title="不充电排查方法",
        description="读取已批准的本地手册，整理安全排查所需证据；加载不代表诊断完成。",
        availability="AVAILABLE", input_schema=SkillInput.model_json_schema(),
        output_schema=DiagnosisGuidance.model_json_schema(),
        applicability=("ACTIVE_CONVERSATION", "AUTHORIZED_PUBLIC_CUSTOMER_MESSAGE", "READ_ONLY_MANUALS"),
        allowed_tools=("lookup_manual",),
        allowed_ui_components=("DiagnosticSteps", "QuestionForm", "RiskNotice"), risk_level="LOW",
        failure_exit="型号或安全条件不明时停止具体排查，说明证据缺口并建议人工协助。",
    ),
    ("emotion-assessment", "1.0.0"): SkillDefinition(
        skill_id="emotion-assessment", version="1.0.0", title="情绪辅助评估（契约预备）",
        description="尚未启用识别，不产生情绪判断；未来结果也仅为未核验的服务辅助信号。",
        availability="PREPARED", input_schema=SkillInput.model_json_schema(),
        output_schema=EmotionAssessment.model_json_schema(),
        applicability=("PREPARED_NOT_CALLABLE", "AUTHORIZED_PUBLIC_CUSTOMER_MESSAGE"),
        allowed_tools=(), allowed_ui_components=(), risk_level="LOW",
        failure_exit="保持中性服务表达；不得自动退款、换货、关单或改变协作模式。",
    ),
})

# Kept in source control; never supplied by a user, a model, a URL or a catalog API.
SKILL_INSTRUCTIONS = MappingProxyType({
    ("diagnose-no-charge", "1.0.0"): (
        "本方法仅加载，不代表完成诊断。仅可用 lookup_manual 读取已批准的本地手册。"
        "先核对安全条件、设备型号和端口证据；型号未确认时不得套用 A1229 规格。"
        "发现发热、鼓包、异味或损坏时停止测试并建议人工协助。"
        "区分用户陈述、已核验事实与假设；引用当前获授权消息与手册来源，给出安全可逆的下一步和失败出口。"
        "资料不适用或证据不足时说明限制，不猜测规格，不调用不存在的诊断服务。"
        "不得执行售后动作、自动退款、换货、关单、修改设备事实或改变协作模式；公开答复仍须后端授权。"
    ),
})


def eligible_skills(conversation: Conversation) -> list[SkillDefinition]:
    """Called only after source/owner authorization; no text or emotion heuristics."""
    if conversation.status != "ACTIVE":
        return []
    return [definition for definition in SKILL_REGISTRY.values() if definition.availability == "AVAILABLE"]


class SkillLoadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str
    version: str
    status: Literal["LOADED"] = "LOADED"
    execution_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    instructions: str = Field(min_length=1, max_length=2000)
    allowed_tools: tuple[str, ...]
    allowed_ui_components: tuple[str, ...]


class SkillExecutionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    skill_id: Literal["diagnose-no-charge"]
    version: Literal["1.0.0"]
    status: Literal["LOADED"]
    visibility: Literal["INTERNAL"]
    source_message_ids: list[UUID] = Field(min_length=1, max_length=8)
    execution_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    loaded_at: datetime


class SkillCatalog(BaseModel):
    items: list[SkillDefinition]


class SkillExecutionPage(BaseModel):
    items: list[SkillExecutionRead]
    next_after: str | None = None


class SkillService:
    def __init__(self, session: Session, actor: Principal):
        self.session = session
        self.actor = actor

    def _require_staff(self):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可查看内部 Skill 资料。")

    def catalog(self) -> SkillCatalog:
        self._require_staff()
        return SkillCatalog(items=[item.model_copy(deep=True) for item in SKILL_REGISTRY.values()])

    def executions(self, conversation_id: UUID, after: str | None = None, limit: int = 50) -> SkillExecutionPage:
        """Keyset page ordered by run creation/id and append-only entry position.

        The opaque cursor is run UUID:entry ordinal. Pagination happens in PostgreSQL,
        not by loading every run or returning unfiltered result_payload dictionaries.
        """
        self._require_staff()
        conversation = ConversationService(self.session, self.actor).resource(Conversation, conversation_id)
        if not 1 <= limit <= 100:
            raise ServiceError(422, "分页数量须在 1 至 100 之间。")
        payload = AgentRun.result_payload["skill_executions"]
        array = case((func.jsonb_typeof(payload) == "array", payload),
                     else_=cast(literal("[]"), JSONB))
        entries = func.jsonb_array_elements(array).table_valued(
            "value", with_ordinality="position").render_derived().lateral()
        query = select(AgentRun.id, entries.c.position, entries.c.value).select_from(AgentRun).join(entries, true()).where(
            AgentRun.tenant_id == self.actor.tenant_id, AgentRun.conversation_id == conversation.id,
        )
        if after is not None:
            try:
                if len(after) > 60:
                    raise ValueError
                run_id, position = after.split(":")
                run_id, position = UUID(run_id), int(position)
                if not 1 <= position <= 32:
                    raise ValueError
            except (ValueError, TypeError):
                raise ServiceError(422, "Skill 分页标识无效。") from None
            previous = self.session.scalar(select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.tenant_id == self.actor.tenant_id,
                AgentRun.conversation_id == conversation.id,
            ))
            if previous is None:
                raise ServiceError(422, "Skill 分页标识不属于当前会话。")
            query = query.where(or_(
                AgentRun.created_at > previous.created_at,
                and_(AgentRun.created_at == previous.created_at, AgentRun.id > previous.id),
                and_(AgentRun.id == previous.id, entries.c.position > position),
            ))
        rows = self.session.execute(query.order_by(
            AgentRun.created_at, AgentRun.id, entries.c.position).limit(limit + 1)).all()
        items = []
        for run_id, _, data in rows[:limit]:
            if not isinstance(data, dict):
                continue
            safe = {key: data[key] for key in SkillExecutionRead.model_fields if key in data}
            safe["run_id"] = run_id
            try:
                items.append(SkillExecutionRead.model_validate(safe))
            except ValidationError:
                # A future/invalid execution never exposes arbitrary stored JSON.
                continue
        next_after = f"{rows[limit - 1][0]}:{rows[limit - 1][1]}" if len(rows) > limit else None
        return SkillExecutionPage(items=items, next_after=next_after)
