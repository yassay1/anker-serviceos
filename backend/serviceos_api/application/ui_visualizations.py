"""Server-owned, source-bound payloads for inert visualization components."""

import hashlib
import re
from pathlib import Path
HEATING_SOURCE_ID = "eufy-s1-pro-heating-battery-v1"
HEATING_METRIC_ID = "heating-extra-battery"
HEATING_KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "eufy-s1-pro-heating-metric.md"


def knowledge_source_used_in_run(source_id: str, result_payload: object) -> bool:
    """Require an audited, same-run manual lookup for source-dependent UI proposals."""
    if source_id != HEATING_SOURCE_ID or not isinstance(result_payload, dict):
        return False
    envelopes = result_payload.get("tool_envelopes")
    if not isinstance(envelopes, list):
        return False
    for envelope in envelopes:
        if (not isinstance(envelope, dict) or envelope.get("tool") != "lookup_manual"
                or envelope.get("status") != "OK"):
            continue
        applicability = envelope.get("applicability")
        if not isinstance(applicability, str) or "t8d04" not in applicability.casefold():
            continue
        references = envelope.get("references")
        if not isinstance(references, list):
            continue
        if any(isinstance(reference, dict) and (
            reference.get("entry_key") == HEATING_METRIC_ID or
            reference.get("source_ref") == source_id
        ) for reference in references):
            return True
    return False


def knowledge_metric_chart(source_id: str, verified_models: set[str]) -> dict | None:
    """Return the one allowlisted chart only for a verified applicable product model."""
    if source_id != HEATING_SOURCE_ID or "T8D04" not in {value.upper() for value in verified_models}:
        return None
    try:
        raw = HEATING_KNOWLEDGE_PATH.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    # Git may check out this packaged source with Windows CRLF line endings.
    # Normalize before the line-anchored metric parser runs.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
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
                      "detail": f"客户观察：{verification.observed_result}；核验结论：{verification.decision}",
                      "resource_kind": "CASE_VIEW", "resource_id": case.id, "resource_version": case.version})
        if action is not None:
            edges.append({"source": "service-action", "target": "verification"})
        else:
            edges.append({"source": "case", "target": "verification"})
    return {"nodes": nodes, "edges": edges}


def customer_case_progress(case, task=None, action=None, verification=None) -> dict[str, str]:
    """Describe only customer-safe waiting/progress state from current linked records."""
    status = case.status
    if status == "WAITING_CUSTOMER":
        body = "等待你补充所需信息或反馈当前结果。"
    elif status == "WAITING_EXTERNAL":
        body = "正在等待相关外部处理完成；有更新后会继续告知。"
    elif status in ("RESOLVED", "CLOSED"):
        body = "服务结果已通过现有核验流程确认。" if status == "RESOLVED" else "服务案例已关闭。"
    elif verification is not None and verification.decision == "PENDING":
        body = "售后处理已记录，正在等待你反馈设备当前结果。"
    elif verification is not None and verification.decision == "NOT_RESOLVED":
        body = "你反馈问题仍未解决，服务团队会继续跟进。"
    elif action is not None and action.status == "UNKNOWN":
        body = "售后动作结果尚未确认，正在核对原记录；请勿重复提交。"
    elif action is not None and action.status == "SUCCEEDED":
        body = "售后动作已取得模拟回执，仍需确认实际结果；问题尚未标记为解决。"
    elif action is not None and action.status in ("FAILED", "REJECTED"):
        body = "本次售后动作未完成，服务团队会继续确认可行的下一步。"
    elif task is not None and task.status in ("OPEN", "ASSIGNED"):
        body = "客服正在处理这项服务请求。"
    elif status == "OPEN":
        body = "服务案例已建立，正在确认适用的下一步。"
    else:
        body = "服务团队正在处理；设备问题仍以核验结果为准。"
    return {"title": "当前服务进度", "body": body, "status": status}
