"""Trusted, versioned component catalog. No executable UI or free-form data queries."""

import re
from uuid import UUID

from serviceos_api.application.errors import ServiceError

SCHEMA_VERSION = 1
CATALOG_VERSION = 1
CATALOG = {
    "CaseSummaryCard": ("title", "body", "status", "source", "verification"),
    "EvidenceSummary": ("title", "body", "source", "verification"),
    "QuestionForm": ("title", "body"),
    "RiskAlert": ("title", "body"),
    "ProgressTimeline": ("title", "body", "status"),
    "HandoffSummary": ("title", "body", "status"),
    "ActionBar": ("title", "body"),
}
BINDINGS = {
    "CONVERSATION_VIEW": {"overview", "assistance", "mode"},
    "CASE_VIEW": {"summary", "evidence"},
    "TASK_VIEW": {"handoff", "progress"},
    "AGENT_RUN_VIEW": {"question"},
}
UNSAFE = re.compile(r"<|>|https?://|javascript:|data:|\bon\w+\s*=", re.IGNORECASE)


def safe_text(value: object, *, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or UNSAFE.search(value):
        raise ServiceError(422, "UI 文本含无效或不安全内容。")
    return value.strip()


def validate_components(components: list[dict], audience: str,
                        allowed_refs: dict[tuple[str, UUID], int]) -> list[dict]:
    if not isinstance(components, list) or not 1 <= len(components) <= 12:
        raise ServiceError(422, "UI 组件数量超出限制。")
    ids = set()
    normalized = []
    for item in components:
        if not isinstance(item, dict) or set(item) != {"id", "type", "props", "data_source", "actions", "children"}:
            raise ServiceError(422, "UI 组件结构无效。")
        component_id = item["id"]
        if not isinstance(component_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", component_id) or component_id in ids:
            raise ServiceError(422, "UI 组件 ID 无效或重复。")
        ids.add(component_id)
        kind = item["type"]
        if kind not in CATALOG:
            raise ServiceError(422, "UI 组件不在受信目录中。")
        props = item["props"]
        if not isinstance(props, dict) or set(props) != set(CATALOG[kind]):
            raise ServiceError(422, "UI 组件属性不符合目录。")
        props = {key: safe_text(value) for key, value in props.items()}
        source = item["data_source"]
        if not isinstance(source, dict) or set(source) != {"kind", "resource_id", "resource_version", "binding"}:
            raise ServiceError(422, "UI 数据来源无效。")
        if source["kind"] not in BINDINGS or source["binding"] not in BINDINGS[source["kind"]]:
            raise ServiceError(422, "UI 数据来源未获授权。")
        try:
            resource_id = UUID(str(source["resource_id"]))
        except (ValueError, TypeError, AttributeError):
            raise ServiceError(422, "UI 数据来源资源 ID 无效。") from None
        if allowed_refs.get((source["kind"], resource_id)) != source["resource_version"]:
            raise ServiceError(403, "UI 数据来源与授权资源或版本不符。")
        if audience == "CUSTOMER" and source["kind"] not in ("CONVERSATION_VIEW", "AGENT_RUN_VIEW"):
            raise ServiceError(403, "客户 UI 不能引用内部数据来源。")
        actions = item["actions"]
        if not isinstance(actions, list) or len(actions) > 1:
            raise ServiceError(422, "UI 动作数量无效。")
        if kind != "ActionBar" and actions:
            raise ServiceError(422, "此组件不能发起动作。")
        if kind == "ActionBar":
            expected = {"action_id": "request-human-assistance", "intent": "REQUEST_ASSISTANCE",
                        "input_schema_ref": "serviceos://ui-inputs/assistance-request/v1"}
            if audience != "CUSTOMER" or actions != [expected]:
                raise ServiceError(422, "UI 动作未获授权。")
        children = item["children"]
        if not isinstance(children, list) or len(children) > 4 or any(not isinstance(value, str) for value in children):
            raise ServiceError(422, "UI 组件子节点无效。")
        normalized.append({"id": component_id, "type": kind, "props": props,
                           "data_source": {"kind": source["kind"], "resource_id": str(resource_id),
                                           "resource_version": source["resource_version"],
                                           "binding": source["binding"]},
                           "actions": actions, "children": children})
    by_id = {component["id"]: component for component in normalized}
    def visit(component_id: str, path: set[str], depth: int):
        if depth > 2 or component_id in path or component_id not in by_id:
            raise ServiceError(422, "UI 组件引用存在循环、缺失或过深嵌套。")
        for child in by_id[component_id]["children"]:
            visit(child, path | {component_id}, depth + 1)
    for component_id in by_id:
        visit(component_id, set(), 0)
    return normalized
