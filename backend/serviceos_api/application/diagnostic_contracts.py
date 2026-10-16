"""Versioned, bounded contracts for the delegated diagnostic capability."""

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from serviceos_api.application.contracts import Schema


class DiagnosticCaseRef(Schema):
    case_id: UUID
    version: int = Field(ge=1)
    problem: str = Field(min_length=1, max_length=1000)


class DiagnosticDeviceRef(Schema):
    device_id: UUID
    revision: int = Field(ge=1)
    identity_status: Literal["VERIFIED", "UNVERIFIED"]
    model: str | None = Field(default=None, max_length=120)
    verified_facts: list[str] = Field(default_factory=list, max_length=20)


class DiagnosticEvidenceRef(Schema):
    ref_id: str = Field(min_length=1, max_length=160)
    ref_kind: Literal[
        "CASE_EVIDENCE", "CUSTOMER_STATEMENT", "VERIFIED_DEVICE_FACT", "MANUAL_SOURCE", "EXPERIENCE_CANDIDATE",
    ]
    summary: str = Field(min_length=1, max_length=500)


class DiagnosticExperience(Schema):
    candidate_id: UUID
    candidate_version: int = Field(ge=1)
    source_case_id: UUID
    source_verification_id: UUID
    issue_type: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=3, max_length=160)
    applicable_models: list[str] = Field(min_length=1, max_length=10)
    symptoms: list[str] = Field(min_length=1, max_length=10)
    required_evidence: list[str] = Field(default_factory=list, max_length=10)
    steps: list[str] = Field(min_length=1, max_length=8)
    success_criteria: str = Field(min_length=3, max_length=500)
    failure_exit: str = Field(min_length=3, max_length=500)


class DiagnosticTaskInput(Schema):
    schema_version: Literal[1] = 1
    task_id: UUID
    conversation_id: UUID
    goal: str = Field(min_length=1, max_length=1000)
    case_refs: list[DiagnosticCaseRef] = Field(default_factory=list, max_length=5)
    device_refs: list[DiagnosticDeviceRef] = Field(default_factory=list, max_length=10)
    evidence_refs: list[DiagnosticEvidenceRef] = Field(default_factory=list, max_length=60)
    experience_examples: list[DiagnosticExperience] = Field(default_factory=list, max_length=2)
    public_history: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("goal", "public_history")
    @classmethod
    def trim_untrusted_text(cls, value):
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("diagnostic_text_required")
            return trimmed
        trimmed = [item.strip() if isinstance(item, str) else item for item in value]
        if any(not isinstance(item, str) or not item or len(item) > 500 for item in trimmed):
            raise ValueError("diagnostic_history_item_invalid")
        return trimmed


class DiagnosticResultEvidence(Schema):
    ref_id: str = Field(min_length=1, max_length=160)
    supports: str = Field(min_length=1, max_length=500)


class DiagnosticQuestion(Schema):
    prompt: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return _safe_display_text(value, 500)

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.split()) for value in values]
        if any(not value or len(value) > 80 for value in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("diagnostic_question_options_invalid")
        cleaned = [_safe_display_text(value, 80) for value in cleaned]
        if cleaned and len(cleaned) < 2:
            raise ValueError("diagnostic_question_requires_multiple_options")
        return cleaned


def _safe_display_text(value: str, limit: int) -> str:
    if (not value.strip() or len(value) > limit or re.search(r"<|>|https?://|javascript:|data:|\b\w+@\w+\.\w+", value, re.I)
            or re.search(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", value)):
        raise ValueError("diagnostic_display_text_unsafe")
    return value.strip()


class DiagnosticNextStep(Schema):
    kind: Literal["EXPLAIN", "ASK_CUSTOMER", "REQUEST_EVIDENCE", "SAFETY_STOP", "HUMAN_REVIEW", "NO_ACTION"]
    summary: str = Field(min_length=1, max_length=700)
    safety: str | None = Field(default=None, max_length=500)
    question: DiagnosticQuestion | None = None

    @model_validator(mode="after")
    def require_question_for_customer_wait(self):
        if (self.kind == "ASK_CUSTOMER") != (self.question is not None):
            raise ValueError("diagnostic_customer_question_required_or_unexpected")
        return self


class DiagnosticResult(Schema):
    schema_version: Literal[1] = 1
    task_id: UUID
    assessment: str = Field(min_length=1, max_length=2000)
    certainty: Literal["HYPOTHESIS"] = "HYPOTHESIS"
    confidence_band: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    evidence_refs: list[DiagnosticResultEvidence] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=10)
    next_step: DiagnosticNextStep
    staff_summary: str = Field(min_length=1, max_length=2000)

    @field_validator("assessment", "staff_summary")
    @classmethod
    def trim_result_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("diagnostic_result_text_required")
        return trimmed

    @field_validator("unknowns")
    @classmethod
    def validate_unknowns(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 300 for value in values):
            raise ValueError("diagnostic_unknown_invalid")
        return [value.strip() for value in values]


class SpecialistEvent(Schema):
    """Allowlisted projection of a specialist task; never a tool/model trace."""

    task_id: UUID
    specialist_run_id: UUID
    agent_type: Literal["DIAGNOSTIC"] = "DIAGNOSTIC"
    display_name: Literal["诊断专家"] = "诊断专家"
    stage: Literal["STARTED", "LOOKUP", "RESULT_READY", "WAITING_CUSTOMER", "WAITING_STAFF", "FAILED"]
    summary: str = Field(min_length=1, max_length=500)
    certainty: Literal["HYPOTHESIS", "NONE"]

    @field_validator("summary")
    @classmethod
    def validate_summary_safety(cls, value: str) -> str:
        if ("<" in value or ">" in value or re.search(r"https?://|javascript:|data:|\b\w+@\w+\.\w+", value, re.I)
                or re.search(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", value)):
            raise ValueError("specialist_event_summary_unsafe")
        return value.strip()

    @model_validator(mode="after")
    def authorized_summary(self):
        fixed = {
            "STARTED": "诊断专家已开始分析当前问题。",
            "LOOKUP": "诊断专家正在查阅已批准的售后资料。",
            "WAITING_CUSTOMER": "诊断专家需要补充一项信息。",
            "WAITING_STAFF": "诊断结果需要客服进一步核实。",
            "FAILED": "诊断专家本次分析未完成，服务助手将继续处理。",
        }
        if self.stage in fixed and self.summary != fixed[self.stage]:
            raise ValueError("specialist_event_summary_not_authorized")
        if (self.stage == "RESULT_READY") != (self.certainty == "HYPOTHESIS"):
            raise ValueError("specialist_certainty_invalid")
        return self


def validate_diagnostic_result(result: DiagnosticResult | dict[str, Any], task: DiagnosticTaskInput,
                               additional_allowed_refs: set[str] | None = None) -> DiagnosticResult:
    """Bind model output to this task and its server-authorized evidence references."""
    validated = result if isinstance(result, DiagnosticResult) else DiagnosticResult.model_validate(result)
    if validated.task_id != task.task_id:
        raise ValueError("diagnostic_result_task_mismatch")
    allowed_refs = {reference.ref_id for reference in task.evidence_refs} | (additional_allowed_refs or set())
    if any(reference.ref_id not in allowed_refs for reference in validated.evidence_refs):
        raise ValueError("diagnostic_result_reference_not_authorized")
    return validated
