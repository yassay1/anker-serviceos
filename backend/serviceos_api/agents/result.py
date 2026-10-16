"""Bounded, internal Agent result. A UI proposal is never a published UIDocument."""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_HINTS = frozenset({"QuestionForm", "ChoiceGroup", "DiagnosticSteps", "RiskNotice", "HandoffSummary",
                           "KnowledgeMetricChart", "CaseProcessFlow"})
ALLOWED_KNOWLEDGE_SOURCES = frozenset({"eufy-s1-pro-heating-battery-v1"})
UIHint = Literal["QuestionForm", "ChoiceGroup", "DiagnosticSteps", "RiskNotice", "HandoffSummary",
                 "KnowledgeMetricChart", "CaseProcessFlow"]


class UIOption(TypedDict):
    label: str
    value: str


class UIProposal(TypedDict):
    purpose: str
    audience: Literal["CUSTOMER", "STAFF"]
    fallback_text: str
    component_hints: list[UIHint]
    options: NotRequired[list[UIOption]]
    knowledge_source_id: NotRequired[str]
    case_id: NotRequired[str]


@dataclass(frozen=True)
class AgentResult:
    text: str
    ui_proposal: UIProposal | None = None
    ui_fallback_code: str | None = None
    rich_reply: dict | None = None


class AgentFinalOutput(BaseModel):
    """Typed LangChain final output; UI metadata remains untrusted until app validation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1, max_length=8000)
    ui_proposal: Any | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _text(value)


class AgentOutputInvalidError(RuntimeError):
    """A deterministic final-output failure safe to expose only as an allowlisted code."""

    error_code = "agent_output_invalid"


# Models routinely fence their structured result. The fence must be removed before deciding,
# otherwise the whole object is treated as prose and shown to the customer verbatim.
FENCED = re.compile(r"```[A-Za-z0-9_-]*\s*\n?(?P<body>.*?)\n?```", re.DOTALL)


def _structured_candidate(raw: str) -> str:
    """Prefer a fenced JSON object; otherwise unwrap a fence that spans the whole content."""
    for match in FENCED.finditer(raw):
        body = match.group("body").strip()
        if body.startswith("{"):
            return body
    whole = FENCED.fullmatch(raw)
    return whole.group("body").strip() if whole else raw


def parse_agent_result(content: str) -> AgentResult:
    """Accept plain text; reject malformed structured output without publishing its raw JSON."""
    raw = content.strip()
    if not raw:
        raise ValueError("agent_final_response_empty")
    raw = _structured_candidate(raw)
    if not raw.startswith("{"):
        return AgentResult(_text(raw))
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as error:
        recovered = re.search(r'"text"\s*:\s*("(?:\\.|[^"\\])*")', raw)
        if recovered:
            try:
                return AgentResult(_text(json.loads(recovered.group(1))), ui_fallback_code='rich_result_truncated')
            except (ValueError, TypeError):
                pass
        raise ValueError("agent_result_invalid_json") from error
    if not isinstance(value, dict):
        raise ValueError("agent_result_invalid_shape")
    answer = _text(value.get("text"))
    rich, rich_error = None, None
    if value.get('rich') is not None:
        from serviceos_api.application.rich_reply import RichReply
        try:
            rich = RichReply.model_validate(value['rich']).model_dump(mode='json')
        except (ValueError, TypeError):
            rich_error = 'rich_reply_invalid'
    candidate = value.get("ui_proposal")
    if candidate is None:
        return AgentResult(answer, ui_fallback_code=rich_error, rich_reply=rich)
    try:
        proposal = _ui_proposal(candidate)
    except ValueError:
        return AgentResult(answer, ui_fallback_code="ui_proposal_invalid", rich_reply=rich)
    return AgentResult(answer, ui_proposal=proposal, ui_fallback_code=rich_error, rich_reply=rich)


def parse_agent_payload(payload: Any) -> AgentResult:
    """Convert a validated structured result while retaining the legacy UI fallback rules."""
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="python")
    if not isinstance(payload, dict) or set(payload) - {"text", "ui_proposal"}:
        raise ValueError("agent_result_invalid_shape")
    answer = _text(payload.get("text"))
    candidate = payload.get("ui_proposal")
    if candidate is None:
        return AgentResult(answer)
    try:
        proposal = _ui_proposal(candidate)
    except ValueError:
        return AgentResult(answer, ui_fallback_code="ui_proposal_invalid")
    return AgentResult(answer, ui_proposal=proposal)


# Internal keys that must never reach a customer, whatever the model does with formatting.
INTERNAL_KEYS = ("ui_proposal", "component_hints", "fallback_text", "action_proposals")


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 8000:
        raise ValueError("agent_final_response_invalid_text")
    text = value.strip()
    if any(key in text for key in INTERNAL_KEYS):
        # Failing the run is strictly better than publishing our internal structure.
        raise ValueError("agent_final_response_leaks_internal_keys")
    return text


def _ui_proposal(value: Any) -> UIProposal:
    required = {"purpose", "audience", "fallback_text", "component_hints"}
    if not isinstance(value, dict):
        raise ValueError("ui_proposal_invalid")
    keys = set(value)
    # Everything required, nothing beyond the optional options: an unknown key still fails here.
    if not required <= keys or keys - required - {"options", "knowledge_source_id", "case_id"}:
        raise ValueError("ui_proposal_invalid")
    if value["audience"] not in ("CUSTOMER", "STAFF"):
        raise ValueError("ui_proposal_invalid")
    for key, limit in (("purpose", 160), ("fallback_text", 500)):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > limit:
            raise ValueError("ui_proposal_invalid")
        if re.search(r"<|>|https?://|javascript:|data:|\bon\w+\s*=", value[key], re.IGNORECASE):
            raise ValueError("ui_proposal_invalid")
    hints = value["component_hints"]
    if not isinstance(hints, list) or not 1 <= len(hints) <= 3 or any(
        not isinstance(hint, str) or hint not in ALLOWED_HINTS for hint in hints
    ) or len(set(hints)) != len(hints):
        raise ValueError("ui_proposal_invalid")
    if "options" in value:
        _options(value["options"])
    if "knowledge_source_id" in value and (
        not isinstance(value["knowledge_source_id"], str) or
        value["knowledge_source_id"] not in ALLOWED_KNOWLEDGE_SOURCES or
        "KnowledgeMetricChart" not in hints
    ):
        raise ValueError("ui_proposal_invalid")
    if "case_id" in value and (
        not isinstance(value["case_id"], str) or
        not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value["case_id"], re.IGNORECASE) or
        "CaseProcessFlow" not in hints
    ):
        raise ValueError("ui_proposal_invalid")
    if "KnowledgeMetricChart" in hints and ("knowledge_source_id" not in value or value["audience"] != "CUSTOMER"):
        raise ValueError("ui_proposal_invalid")
    if "CaseProcessFlow" in hints and ("case_id" not in value or value["audience"] != "STAFF"):
        raise ValueError("ui_proposal_invalid")
    return cast(UIProposal, value)


def _options(value: Any) -> list[dict[str, str]]:
    """Bounded, inert choices. The value is a slug; the label is what the customer sends."""
    if not isinstance(value, list) or not 2 <= len(value) <= 5:
        raise ValueError("ui_proposal_invalid")
    labels, values = set(), set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"label", "value"}:
            raise ValueError("ui_proposal_invalid")
        label, slug = item["label"], item["value"]
        if not isinstance(label, str) or not label.strip() or len(label) > 40:
            raise ValueError("ui_proposal_invalid")
        if re.search(r"<|>|https?://|javascript:|data:|\bon\w+\s*=", label, re.IGNORECASE):
            raise ValueError("ui_proposal_invalid")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]{1,32}", slug):
            raise ValueError("ui_proposal_invalid")
        if label.strip() in labels or slug in values:
            raise ValueError("ui_proposal_invalid")
        labels.add(label.strip())
        values.add(slug)
    return value
