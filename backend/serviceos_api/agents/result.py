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


def _ui_proposal(value: Any) -> dict[str, Any]:
    required = {"purpose", "audience", "fallback_text", "component_hints"}
    if not isinstance(value, dict):
        raise ValueError("ui_proposal_invalid")
    keys = set(value)
    # Everything required, nothing beyond the optional options: an unknown key still fails here.
    if not required <= keys or keys - required - {"options"}:
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
    return value


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
