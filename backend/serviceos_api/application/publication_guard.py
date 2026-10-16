"""Pre-publication guard: grounding + request coverage before customer-visible replies.

Design anchors: RAGAS/FActScore-style faithfulness (v1 = deterministic entity grounding),
IFEval-style verifiable request checklist via a bounded verifier call, and a quality-gate
with maker-checker override. Fail-closed: any unmatched entity, unaddressed request,
ungrounded promise or verifier failure blocks publication into audited review.
When no LLM provider is configured the coverage leg is skipped (no model reply can exist
there), while deterministic grounding still applies.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.integrations.http_clients import post_json

from serviceos_api.persistence.knowledge_models import KnowledgeSegment
from serviceos_api.persistence.models import (
    AgentRun, CaseConversation, CaseDevice, CaseEvidence, DeviceFact,
    ServiceCase,
)
from serviceos_api.settings import Settings

MODEL_PATTERNS = (r"\bT\d{4}[A-Za-z0-9\-]*\b", r"\bT8D\d{2}\b", r"\bE\d{2,3}\b",
                  r"\bX\d{2}\s?Pro\b", r"\bS1\s?Pro\b")
DATE_PATTERNS = (r"\b\d{4}-\d{2}-\d{2}\b", r"\d{4}年\d{1,2}月\d{1,2}日")
NUMBER_PATTERN = r"\d+(?:\.\d+)?\s*(?:%|分钟|minutes|min|小时|hours|天|days|Pa)"
ERROR_PATTERN = r"(?:错误码|error\s*code)\s*(\d{4})"

VERIFIER_SYSTEM = (
    "You verify a customer-service reply against the customer's message. "
    "Output STRICT JSON only: {\"requests\": [{\"text\": str, \"addressed\": bool, "
    "\"reply_span\": str | null}], \"ungrounded_promises\": [str]}. "
    "requests = every explicit request or question in the customer message. "
    "addressed=true when the reply: answers it; OR asks for the specific missing information "
    "needed to proceed (e.g. order number, model); OR explicitly explains it is out of scope and "
    "offers an alternative; OR defers it to a human with a next step. addressed=false only when the "
    "reply silently ignores the request. "
    "ungrounded_promises = promised outcomes, deadlines, refunds, repairs or warranties that the "
    "reply does not tie to a stated evidence source."
)


@dataclass(frozen=True)
class Entity:
    kind: str
    raw: str
    norm: str


@dataclass
class GuardOutcome:
    decision: str
    reason_codes: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    verifier: dict = field(default_factory=dict)
    latency_ms: int = 0


def _norm_date(raw: str) -> str:
    digits = re.findall(r"\d+", raw)
    if len(digits) == 3:
        try:
            return date(int(digits[0]), int(digits[1]), int(digits[2])).isoformat()
        except ValueError:
            return raw
    return raw


def _norm_number(raw: str) -> str:
    match = re.match(r"(\d+(?:\.\d+)?)\s*(.*)$", raw)
    if not match:
        return raw
    value, unit = match.groups()
    unit = {"分钟": "min", "minutes": "min", "min": "min", "小时": "h", "hours": "h",
            "天": "d", "days": "d", "%": "%", "Pa": "Pa"}.get(unit.strip(), unit.strip())
    return f"{float(value):g}{unit}"


def extract_entities(text: str) -> list[Entity]:
    entities: list[Entity] = []
    for pattern in MODEL_PATTERNS:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            entities.append(Entity("model", match, match.upper().replace(" ", "")))
    for pattern in DATE_PATTERNS:
        for match in re.findall(pattern, text):
            entities.append(Entity("date", match, _norm_date(match)))
    for match in re.findall(NUMBER_PATTERN, text):
        entities.append(Entity("number", match, _norm_number(match)))
    for match in re.findall(ERROR_PATTERN, text, flags=re.IGNORECASE):
        entities.append(Entity("error_code", match, match))
    return entities


class CoverageVerifier:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    def verify(self, customer_text: str, reply: str) -> dict | None:
        for attempt in range(2):
            try:
                response = post_json(
                    f"{self.settings.llm_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                    payload={
                        "model": self.settings.fast_or_llm_model,
                        "temperature": 0,
                        "max_completion_tokens": 400,
                        "messages": [
                            {"role": "system", "content": VERIFIER_SYSTEM},
                            {"role": "user", "content":
                                f"CUSTOMER MESSAGE:\n{customer_text[:2000]}\n\nREPLY:\n{reply[:4000]}"},
                        ],
                    },
                    timeout=self.settings.llm_timeout_seconds,
                    transport=self._transport,
                )
                response.raise_for_status()
                payload = response.json()
                content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()))
                if not isinstance(parsed, dict) or not isinstance(parsed.get("requests"), list):
                    return None
                return parsed
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                if attempt == 0:
                    continue
                return None
        return None


class PublicationGuard:
    def __init__(self, session: Session, settings: Settings, tenant_id: UUID,
                 verifier: CoverageVerifier | None = None):
        self.session = session
        self.settings = settings
        self.tenant_id = tenant_id
        self._verifier = verifier

    def evidence_bundle(self, run: AgentRun, conversation_id: UUID, customer_text: str) -> list[str]:
        payload = run.result_payload or {}
        bundle: list[str] = [customer_text]
        keys = [ref.get("entry_key") for ref in payload.get("knowledge_references", []) or []]
        if keys:
            for content, models in self.session.execute(select(
                    KnowledgeSegment.content, KnowledgeSegment.models).where(
                    KnowledgeSegment.entry_key.in_(keys))).all():
                bundle.append(content)
                # PN metadata is authoritative provenance: a referenced segment whose
                # model list contains a code grounds mentions of that code.
                if models:
                    bundle.append(" ".join(str(model).upper() for model in models))
        for envelope in payload.get("tool_envelopes", []) or []:
            bundle.extend(envelope.get("notes", []) or [])
            bundle.extend(envelope.get("items", []) or [])
        case_ids = [row.case_id for row in self.session.scalars(select(CaseConversation).where(
            CaseConversation.conversation_id == conversation_id,
            CaseConversation.tenant_id == self.tenant_id)).all()]
        if case_ids:
            for fact in self.session.scalars(select(DeviceFact).where(
                    DeviceFact.tenant_id == self.tenant_id,
                    DeviceFact.device_id.in_(select(CaseDevice.device_id).where(
                        CaseDevice.case_id.in_(case_ids))),
                    DeviceFact.validity == "VERIFIED")).all():
                bundle.append(f"{fact.fact_key}: {json.dumps(fact.value, ensure_ascii=False)}")
            for evidence in self.session.scalars(select(CaseEvidence).where(
                    CaseEvidence.tenant_id == self.tenant_id, CaseEvidence.case_id.in_(case_ids))).all():
                bundle.append(evidence.summary or evidence.claim_type or "")
        return [text for text in bundle if text]

    def _grounded(self, entity: Entity, bundle: list[str]) -> bool:
        for text in bundle:
            if entity.kind in ("model", "error_code"):
                if entity.norm in text.upper().replace(" ", ""):
                    return True
            elif entity.kind == "date":
                if any(entity.norm == _norm_date(match)
                       for pattern in DATE_PATTERNS for match in re.findall(pattern, text)):
                    return True
            elif entity.kind == "number":
                if any(entity.norm == _norm_number(match)
                       for match in re.findall(NUMBER_PATTERN, text)):
                    return True
        return False

    def check(self, reply: str, run: AgentRun, conversation_id: UUID, customer_text: str) -> GuardOutcome:
        started = time.monotonic()
        reasons: list[str] = []
        bundle = self.evidence_bundle(run, conversation_id, customer_text)
        customer_norms = {entity.norm for entity in extract_entities(customer_text)}
        entities_detail = []
        for entity in extract_entities(reply):
            echoed = entity.norm in customer_norms
            grounded = echoed or self._grounded(entity, bundle)
            entities_detail.append({"kind": entity.kind, "raw": entity.raw,
                                    "echoed": echoed, "grounded": grounded})
            if not grounded:
                reasons.append("UNGROUNDED_ENTITY")
        verifier_detail: dict = {"status": "skipped_no_provider"}
        if self.settings.llm_configured:
            verifier = self._verifier or CoverageVerifier(self.settings)
            verdict = verifier.verify(customer_text, reply)
            if verdict is None:
                reasons.append("VERIFIER_UNAVAILABLE")
                verifier_detail = {"status": "unavailable"}
            else:
                unaddressed = [item.get("text") for item in verdict.get("requests", [])
                               if isinstance(item, dict) and not item.get("addressed")]
                promises = [item for item in verdict.get("ungrounded_promises", []) if isinstance(item, str)]
                verifier_detail = {"status": "ok", "unaddressed": unaddressed, "promises": promises}
                if unaddressed or promises:
                    reasons.append("UNCOVERED_REQUEST")
        decision = "BLOCKED" if reasons else "PASSED"
        return GuardOutcome(decision=decision, reason_codes=sorted(set(reasons)),
                            entities=entities_detail, verifier=verifier_detail,
                            latency_ms=int((time.monotonic() - started) * 1000))
