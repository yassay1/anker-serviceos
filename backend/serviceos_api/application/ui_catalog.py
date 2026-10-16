"""Trusted, versioned component catalog. No executable UI or free-form data queries."""

import re
from uuid import UUID

from serviceos_api.application.errors import ServiceError

SCHEMA_VERSION = 1
# Version 3 adds bounded chart and flow payloads. Older published documents remain valid.
CATALOG_VERSION = 3
CATALOG = {
    "CaseSummaryCard": ("title", "body", "status", "source", "verification"),
    "EvidenceSummary": ("title", "body", "source", "verification"),
    "QuestionForm": ("title", "body"),
    "ChoiceGroup": ("title", "body"),
    "RiskAlert": ("title", "body"),
    "ProgressTimeline": ("title", "body", "status"),
    "HandoffSummary": ("title", "body", "status"),
    "ActionBar": ("title", "body"),
    "KnowledgeMetricChart": ("title", "body"),
    "CaseProcessFlow": ("title", "body"),
}
# Only these types may carry options, and they still may not carry actions.
OPTION_TYPES = ("ChoiceGroup",)
MIN_OPTIONS = 2
MAX_OPTIONS = 5
BINDINGS = {
    "CONVERSATION_VIEW": {"overview", "assistance", "mode"},
    "CASE_VIEW": {"summary", "evidence", "process_flow"},
    "TASK_VIEW": {"handoff", "progress"},
    "AGENT_RUN_VIEW": {"question", "metric"},
}
FLOW_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "WAITING", "COMPLETED", "FAILED", "UNKNOWN", "NOT_APPLICABLE"}
FLOW_NODE_IDS = {"case", "human-task", "service-action", "verification"}
HEATING_POINTS = [{"label": "5 分钟", "value": 10.0}, {"label": "10 分钟", "value": 20.0},
                  {"label": "15 分钟", "value": 30.0}]
UNSAFE = re.compile(r"<|>|https?://|javascript:|data:|\bon\w+\s*=", re.IGNORECASE)


def safe_text(value: object, *, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or UNSAFE.search(value):
        raise ServiceError(422, "UI 文本含无效或不安全内容。")
    return value.strip()


def _safe_options(value: object) -> list[dict[str, str]]:
    """Inert choices only: a label the customer may send and a stable slug. No actions.

    An empty list means the component carries no choices at all; a non-empty list
    must be a real choice, so a single option is rejected.
    """
    if not isinstance(value, list) or len(value) > MAX_OPTIONS:
        raise ServiceError(422, "UI 选项数量超出限制。")
    if value and len(value) < MIN_OPTIONS:
        raise ServiceError(422, "UI 选项数量不足。")
    labels, slugs = set(), set()
    normalized = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"label", "value"}:
            raise ServiceError(422, "UI 选项结构无效。")
        label, slug = item["label"], item["value"]
        if not isinstance(label, str) or not label.strip() or len(label) > 40 or UNSAFE.search(label):
            raise ServiceError(422, "UI 选项文本无效或不安全。")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]{1,32}", slug):
            raise ServiceError(422, "UI 选项标识无效。")
        if label.strip() in labels or slug in slugs:
            raise ServiceError(422, "UI 选项重复。")
        labels.add(label.strip())
        slugs.add(slug)
        normalized.append({"label": label.strip(), "value": slug})
    return normalized


def validate_components(components: list[dict], audience: str,
                        allowed_refs: dict[tuple[str, UUID], int]) -> list[dict]:
    if not isinstance(components, list) or not 1 <= len(components) <= 12:
        raise ServiceError(422, "UI 组件数量超出限制。")
    ids = set()
    normalized = []
    for item in components:
        if not isinstance(item, dict):
            raise ServiceError(422, "UI 组件结构无效。")
        component_keys = set(item)
        # options is optional and stays outside props: prop values are always strings,
        # and a type that is not allowed to carry them must not smuggle them in.
        if component_keys - {"options", "chart", "flow"} != {"id", "type", "props", "data_source", "actions", "children"}:
            raise ServiceError(422, "UI 组件结构无效。")
        component_id = item["id"]
        if not isinstance(component_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", component_id) or component_id in ids:
            raise ServiceError(422, "UI 组件 ID 无效或重复。")
        ids.add(component_id)
        kind = item["type"]
        if kind not in CATALOG:
            raise ServiceError(422, "UI 组件不在受信目录中。")
        options = item.get("options", [])
        if options and kind not in OPTION_TYPES:
            raise ServiceError(422, "此组件不能携带选项。")
        options = _safe_options(options)
        if kind in OPTION_TYPES and not options:
            raise ServiceError(422, "UI 选项数量不足。")
        chart, flow = item.get("chart"), item.get("flow")
        if kind == "KnowledgeMetricChart":
            if audience != "CUSTOMER":
                raise ServiceError(403, "知识指标图表仅供客户查看。")
            _validate_chart(chart)
            if flow is not None:
                raise ServiceError(422, "图表不能包含流程数据。")
        elif chart is not None:
            raise ServiceError(422, "此组件不能携带图表数据。")
        if kind == "CaseProcessFlow":
            if audience != "STAFF":
                raise ServiceError(403, "流程图仅供客服查看。")
            _validate_flow(flow, allowed_refs)
        elif flow is not None:
            raise ServiceError(422, "此组件不能携带流程数据。")
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
        if kind == "KnowledgeMetricChart" and (source["kind"], source["binding"]) != ("AGENT_RUN_VIEW", "metric"):
            raise ServiceError(422, "知识图表必须引用获准的 AgentRun 来源。")
        if kind == "CaseProcessFlow" and (source["kind"], source["binding"]) != ("CASE_VIEW", "process_flow"):
            raise ServiceError(422, "流程图必须引用获准的 Case 来源。")
        if kind == "CaseProcessFlow":
            if not any(node["id"] == "case" for node in flow["nodes"]):
                raise ServiceError(422, "流程图缺少案例节点。")
            case_node = next(node for node in flow["nodes"] if node["id"] == "case")
            if UUID(str(case_node["resource_id"])) != resource_id or case_node["resource_version"] != source["resource_version"]:
                raise ServiceError(422, "流程图案例节点必须与组件来源一致。")
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
                           "actions": actions, "children": children, "options": options,
                           "chart": chart, "flow": flow})
    by_id = {component["id"]: component for component in normalized}
    def visit(component_id: str, path: set[str], depth: int):
        if depth > 2 or component_id in path or component_id not in by_id:
            raise ServiceError(422, "UI 组件引用存在循环、缺失或过深嵌套。")
        for child in by_id[component_id]["children"]:
            visit(child, path | {component_id}, depth + 1)
    for component_id in by_id:
        visit(component_id, set(), 0)
    return normalized


def _validate_chart(chart: object) -> None:
    required = {"metric_id", "chart_type", "x_axis_label", "y_axis_label", "unit", "points",
                "source_label", "source_version", "note"}
    if not isinstance(chart, dict) or set(chart) != required:
        raise ServiceError(422, "图表数据结构无效。")
    if (chart["metric_id"] != "heating-extra-battery" or chart["chart_type"] != "BAR" or chart["unit"] != "%" or
            chart["x_axis_label"] != "加热时长（分钟）" or chart["y_axis_label"] != "额外电量消耗" or
            chart["points"] != HEATING_POINTS):
        raise ServiceError(422, "图表数据与受信知识来源不符。")
    for key, limit in (("source_label", 180), ("source_version", 64), ("note", 240)):
        safe_text(chart[key], limit=limit)
    if not re.fullmatch(r"[0-9a-f]{16}", chart["source_version"]):
        raise ServiceError(422, "图表来源版本无效。")


def _validate_flow(flow: object, allowed_refs: dict[tuple[str, UUID], int]) -> None:
    if not isinstance(flow, dict) or set(flow) != {"nodes", "edges"}:
        raise ServiceError(422, "流程图数据结构无效。")
    nodes, edges = flow["nodes"], flow["edges"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8 or not isinstance(edges, list) or len(edges) > 8:
        raise ServiceError(422, "流程图规模无效。")
    ids, normalized = set(), []
    required = {"id", "label", "status", "detail", "resource_kind", "resource_id", "resource_version"}
    for node in nodes:
        if (not isinstance(node, dict) or set(node) != required or not isinstance(node["id"], str) or
                node["id"] not in FLOW_NODE_IDS or node["id"] in ids):
            raise ServiceError(422, "流程节点结构无效。")
        if (not isinstance(node["status"], str) or node["status"] not in FLOW_STATUSES or
                node["resource_kind"] not in ("CASE_VIEW", "TASK_VIEW") or
                not isinstance(node["resource_version"], int) or isinstance(node["resource_version"], bool) or
                node["resource_version"] < 1):
            raise ServiceError(422, "流程节点状态或来源无效。")
        label, detail = safe_text(node["label"], limit=80), safe_text(node["detail"], limit=240)
        try:
            resource_id = UUID(str(node["resource_id"]))
        except (ValueError, TypeError, AttributeError):
            raise ServiceError(422, "流程节点资源 ID 无效。") from None
        if allowed_refs.get((node["resource_kind"], resource_id)) != node["resource_version"]:
            raise ServiceError(403, "流程节点引用了未授权或过期资源。")
        if node["id"] == "human-task" and node["resource_kind"] != "TASK_VIEW":
            raise ServiceError(422, "人工任务节点来源无效。")
        if node["id"] != "human-task" and node["resource_kind"] != "CASE_VIEW":
            raise ServiceError(422, "流程节点必须引用所属案例。")
        ids.add(node["id"])
        normalized.append({**node, "label": label, "detail": detail, "resource_id": str(resource_id)})
    pairs, adjacency = set(), {node_id: [] for node_id in ids}
    for edge in edges:
        if (not isinstance(edge, dict) or set(edge) != {"source", "target"} or
                not isinstance(edge["source"], str) or not isinstance(edge["target"], str)):
            raise ServiceError(422, "流程连线结构无效。")
        source, target = edge["source"], edge["target"]
        pair = (source, target)
        if source not in ids or target not in ids or source == target or pair in pairs:
            raise ServiceError(422, "流程连线引用无效。")
        pairs.add(pair)
        adjacency[source].append(target)
    visiting, visited = set(), set()
    def visit(node_id: str):
        if node_id in visiting:
            raise ServiceError(422, "流程图不能包含循环。")
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in adjacency[node_id]:
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)
    for node_id in ids:
        visit(node_id)
