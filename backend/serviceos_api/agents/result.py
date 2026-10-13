"""Bounded, internal Agent result. A UI proposal is never a published UIDocument."""

import json
import re
from dataclasses import dataclass
from typing import Any


ALLOWED_HINTS = frozenset({"QuestionForm", "ChoiceGroup", "DiagnosticSteps", "RiskNotice", "HandoffSummary"})


@dataclass(frozen=True)
class AgentResult:
    text: str
    ui_proposal: dict[str, Any] | None = None
    ui_fallback_code: str | None = None


def parse_agent_result(content: str) -> AgentResult:
    """Accept plain text; reject malformed structured output without publishing its raw JSON."""
    raw = content.strip()
    if not raw:
        raise ValueError("agent_final_response_empty")
    if not raw.startswith("{"):
        return AgentResult(_text(raw))
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise ValueError("agent_result_invalid_json") from error
    if not isinstance(value, dict):
        raise ValueError("agent_result_invalid_shape")
    answer = _text(value.get("text"))
    candidate = value.get("ui_proposal")
    if candidate is None:
        return AgentResult(answer)
    try:
        proposal = _ui_proposal(candidate)
    except ValueError:
        return AgentResult(answer, ui_fallback_code="ui_proposal_invalid")
    return AgentResult(answer, ui_proposal=proposal)


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 8000:
        raise ValueError("agent_final_response_invalid_text")
    return value.strip()


def _ui_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"purpose", "audience", "fallback_text", "component_hints"}:
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
    return value
