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
