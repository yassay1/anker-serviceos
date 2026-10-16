from copy import deepcopy
from uuid import uuid4

import pytest

from serviceos_api.application.errors import ServiceError
from serviceos_api.application.ui_catalog import validate_components


def component(conversation_id):
    return {"id": "request-assistance", "type": "ActionBar",
            "props": {"title": "人工协助", "body": "创建人工任务"},
            "data_source": {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation_id),
                            "resource_version": 1, "binding": "assistance"},
            "actions": [{"action_id": "request-human-assistance", "intent": "REQUEST_ASSISTANCE",
                         "input_schema_ref": "serviceos://ui-inputs/assistance-request/v1"}],
            "children": []}


def test_catalog_rejects_unknown_code_and_unauthorized_source():
    conversation_id = uuid4()
    allowed = {("CONVERSATION_VIEW", conversation_id): 1}
    valid = component(conversation_id)
    assert validate_components([valid], "CUSTOMER", allowed)[0]["type"] == "ActionBar"
    unknown = deepcopy(valid)
    unknown["type"] = "RemoteHTML"
    with pytest.raises(ServiceError):
        validate_components([unknown], "CUSTOMER", allowed)
    code = deepcopy(valid)
    code["props"]["body"] = "<script>alert(1)</script>"
    with pytest.raises(ServiceError):
        validate_components([code], "CUSTOMER", allowed)
    source = deepcopy(valid)
    source["data_source"]["resource_id"] = str(uuid4())
    with pytest.raises(ServiceError):
        validate_components([source], "CUSTOMER", allowed)
    stale = deepcopy(valid)
    stale["data_source"]["resource_version"] = 2
    with pytest.raises(ServiceError):
        validate_components([stale], "CUSTOMER", allowed)


def choice(run_id, options, **overrides):
    value = {"id": "agent-choice", "type": "ChoiceGroup",
             "props": {"title": "下一步需要的信息", "body": "请选择最接近的情况"},
             "data_source": {"kind": "AGENT_RUN_VIEW", "resource_id": str(run_id),
                             "resource_version": 1, "binding": "question"},
             "actions": [], "children": [], "options": options}
    value.update(overrides)
    return value


def test_choice_group_carries_inert_options_only():
    run_id = uuid4()
    allowed = {("AGENT_RUN_VIEW", run_id): 1}
    options = [{"label": "完全不亮", "value": "no-light"}, {"label": "常亮", "value": "steady"}]
    result = validate_components([choice(run_id, options)], "CUSTOMER", allowed)[0]
    assert result["type"] == "ChoiceGroup" and result["options"] == options
    assert result["actions"] == [], "a choice group must not carry an action"


@pytest.mark.parametrize("options", [
    [],
    [{"label": "只有一个", "value": "only"}],
    [{"label": f"选项{n}", "value": f"c-{n}"} for n in range(6)],
    [{"label": "x", "value": "Not A Slug"}],
    [{"label": "<b>粗体</b>", "value": "ok"}],
    [{"label": "重复", "value": "ok"}, {"label": "重复", "value": "ok-2"}],
    [{"label": "甲", "value": "same"}, {"label": "乙", "value": "same"}],
    [{"label": "x", "value": "ok", "endpoint": "/api/v1/anything"}],
])
def test_choice_group_rejects_unbounded_or_executable_options(options):
    run_id = uuid4()
    allowed = {("AGENT_RUN_VIEW", run_id): 1}
    with pytest.raises(ServiceError):
        validate_components([choice(run_id, options)], "CUSTOMER", allowed)


def test_only_choice_group_may_carry_options():
    conversation_id = uuid4()
    allowed = {("CONVERSATION_VIEW", conversation_id): 1}
    smuggling = component(conversation_id)
    smuggling["options"] = [{"label": "甲", "value": "a"}, {"label": "乙", "value": "b"}]
    with pytest.raises(ServiceError):
        validate_components([smuggling], "CUSTOMER", allowed)


def metric_chart(run_id):
    return {"id": "knowledge-metric", "type": "KnowledgeMetricChart",
            "props": {"title": "额外电量消耗估算", "body": "已发布知识条目的近似值。"},
            "data_source": {"kind": "AGENT_RUN_VIEW", "resource_id": str(run_id),
                            "resource_version": 1, "binding": "metric"},
            "actions": [], "children": [],
            "chart": {"metric_id": "heating-extra-battery", "chart_type": "BAR",
                      "x_axis_label": "加热时长（分钟）", "y_axis_label": "额外电量消耗", "unit": "%",
                      "points": [{"label": "5 分钟", "value": 10.0}, {"label": "10 分钟", "value": 20.0},
                                 {"label": "15 分钟", "value": 30.0}],
                      "source_label": "已发布 S1 Pro 知识库条目", "source_version": "a" * 16,
                      "note": "近似估算，不是设备遥测。"}}


def test_knowledge_metric_chart_is_fixed_source_bound_and_inert():
    run_id = uuid4()
    allowed = {("AGENT_RUN_VIEW", run_id): 1}
    result = validate_components([metric_chart(run_id)], "CUSTOMER", allowed)[0]
    assert result["chart"]["metric_id"] == "heating-extra-battery"
    assert result["actions"] == []
    for change in ({"points": [{"label": "5 分钟", "value": 99.0}]},
                   {"unit": "Wh"}, {"source_version": "unknown"}):
        invalid = metric_chart(run_id)
        invalid["chart"].update(change)
        with pytest.raises(ServiceError):
            validate_components([invalid], "CUSTOMER", allowed)
    invalid_source = metric_chart(run_id)
    invalid_source["data_source"]["binding"] = "question"
    with pytest.raises(ServiceError):
        validate_components([invalid_source], "CUSTOMER", allowed)
    with pytest.raises(ServiceError):
        validate_components([metric_chart(run_id)], "STAFF", allowed)


def test_case_process_flow_is_staff_only_and_validates_authorized_dag():
    case_id, task_id = uuid4(), uuid4()
    allowed = {("CASE_VIEW", case_id): 3, ("TASK_VIEW", task_id): 2}
    value = {"id": "case-flow", "type": "CaseProcessFlow",
             "props": {"title": "案例办理流程", "body": "来源于实际状态记录。"},
             "data_source": {"kind": "CASE_VIEW", "resource_id": str(case_id),
                             "resource_version": 3, "binding": "process_flow"},
             "actions": [], "children": [],
             "flow": {"nodes": [
                 {"id": "case", "label": "服务案例", "status": "IN_PROGRESS", "detail": "当前状态：IN_PROGRESS",
                  "resource_kind": "CASE_VIEW", "resource_id": str(case_id), "resource_version": 3},
                 {"id": "human-task", "label": "人工协作", "status": "WAITING", "detail": "任务状态：OPEN",
                  "resource_kind": "TASK_VIEW", "resource_id": str(task_id), "resource_version": 2}],
                 "edges": [{"source": "case", "target": "human-task"}]}}
    result = validate_components([value], "STAFF", allowed)[0]
    assert result["flow"]["edges"] == [{"source": "case", "target": "human-task"}]
    server_owned = deepcopy(value)
    server_owned["flow"]["nodes"][0]["resource_id"] = case_id
    validate_components([server_owned], "STAFF", allowed)
    with pytest.raises(ServiceError):
        validate_components([value], "CUSTOMER", allowed)
    cyclic = deepcopy(value)
    cyclic["flow"]["edges"].append({"source": "human-task", "target": "case"})
    with pytest.raises(ServiceError):
        validate_components([cyclic], "STAFF", allowed)
    unlinked = deepcopy(value)
    unlinked["flow"]["nodes"][1]["resource_id"] = str(uuid4())
    with pytest.raises(ServiceError):
        validate_components([unlinked], "STAFF", allowed)
    other_case_id = uuid4()
    mismatched_case = deepcopy(value)
    mismatched_case["flow"]["nodes"][0]["resource_id"] = str(other_case_id)
    allowed_with_other_case = {**allowed, ("CASE_VIEW", other_case_id): 3}
    with pytest.raises(ServiceError):
        validate_components([mismatched_case], "STAFF", allowed_with_other_case)
    missing_case = deepcopy(value)
    missing_case["flow"]["nodes"] = missing_case["flow"]["nodes"][1:]
    missing_case["flow"]["edges"] = []
    with pytest.raises(ServiceError):
        validate_components([missing_case], "STAFF", allowed)
    malformed = deepcopy(value)
    malformed["flow"]["edges"][0]["source"] = []
    with pytest.raises(ServiceError):
        validate_components([malformed], "STAFF", allowed)
    malformed = deepcopy(value)
    malformed["flow"]["nodes"][0]["id"] = []
    with pytest.raises(ServiceError):
        validate_components([malformed], "STAFF", allowed)
