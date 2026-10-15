"""Server-owned, source-bound payloads for inert visualization components."""

import hashlib
import re
from pathlib import Path
HEATING_SOURCE_ID = "eufy-s1-pro-heating-battery-v1"
HEATING_KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "eufy-s1-pro-heating-metric.md"


def knowledge_metric_chart(source_id: str, verified_models: set[str]) -> dict | None:
    """Return the one allowlisted chart only for a verified applicable product model."""
    if source_id != HEATING_SOURCE_ID or "T8D04" not in {value.upper() for value in verified_models}:
        return None
    try:
        raw = HEATING_KNOWLEDGE_PATH.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    required_markers = (
        f"Source ID: `{HEATING_SOURCE_ID}`", "Applicability: verified model `T8D04` only",
        "Publication status: Published", "Consumer visibility: Visible",
        "Metric ID: `heating-extra-battery`",
    )
    if any(marker not in text for marker in required_markers):
        return None
    points = []
    for minutes, percent in re.findall(r"(?m)^Point: (5|10|15) minutes = (10|20|30) percent$", text):
        points.append({"label": f"{minutes} 分钟", "value": float(percent)})
    expected = [{"label": "5 分钟", "value": 10.0}, {"label": "10 分钟", "value": 20.0},
                {"label": "15 分钟", "value": 30.0}]
    if points != expected:
        return None
    source_record = next((line.removeprefix("Source record: ") for line in text.splitlines()
                          if line.startswith("Source record: ")), "")
    if not source_record:
        return None
    return {
        "metric_id": "heating-extra-battery", "chart_type": "BAR",
        "x_axis_label": "加热时长（分钟）", "y_axis_label": "额外电量消耗", "unit": "%",
        "points": points, "source_label": source_record[:180],
        "source_version": hashlib.sha256(raw).hexdigest()[:16],
        "note": "来自提供的知识条目的近似估算，不是个人设备遥测；不要外推到其他时长。",
    }


def case_process_flow(case, task=None, action=None, verification=None) -> dict:
    """Project current durable states. It does not infer completion from UI or agent text."""
    case_state = ("COMPLETED" if case.status in ("RESOLVED", "CLOSED") else
                  "WAITING" if case.status in ("WAITING_CUSTOMER", "WAITING_EXTERNAL") else "IN_PROGRESS")
    nodes = [{"id": "case", "label": "服务案例", "status": case_state,
              "detail": f"当前案例状态：{case.status}", "resource_kind": "CASE_VIEW",
              "resource_id": case.id, "resource_version": case.version}]
    edges = []
    if task is not None:
        task_state = {"OPEN": "WAITING", "ASSIGNED": "IN_PROGRESS", "CLOSED": "COMPLETED"}.get(task.status, "UNKNOWN")
        nodes.append({"id": "human-task", "label": "人工协作", "status": task_state,
                      "detail": f"当前任务状态：{task.status}", "resource_kind": "TASK_VIEW",
                      "resource_id": task.id, "resource_version": task.version})
        edges.append({"source": "case", "target": "human-task"})
    if action is not None:
        action_state = {"WAITING_APPROVAL": "WAITING", "APPROVED": "IN_PROGRESS", "EXECUTING": "IN_PROGRESS",
                        "UNKNOWN": "UNKNOWN", "SUCCEEDED": "COMPLETED", "FAILED": "FAILED",
                        "REJECTED": "FAILED"}.get(action.status, "UNKNOWN")
        nodes.append({"id": "service-action", "label": "售后动作（Mock）", "status": action_state,
                      "detail": f"模拟动作状态：{action.status}", "resource_kind": "CASE_VIEW",
                      "resource_id": case.id, "resource_version": case.version})
        edges.append({"source": "case", "target": "service-action"})
    if verification is not None:
        verify_state = {"VERIFIED_RESOLVED": "COMPLETED", "NOT_RESOLVED": "FAILED", "PENDING": "WAITING"}.get(
            verification.decision, "UNKNOWN")
        nodes.append({"id": "verification", "label": "结果核验", "status": verify_state,
                      "detail": f"核验结论：{verification.decision}",
                      "resource_kind": "CASE_VIEW", "resource_id": case.id, "resource_version": case.version})
        if action is not None:
            edges.append({"source": "service-action", "target": "verification"})
        else:
            edges.append({"source": "case", "target": "verification"})
    return {"nodes": nodes, "edges": edges}
