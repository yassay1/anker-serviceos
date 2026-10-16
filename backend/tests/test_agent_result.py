import json

import pytest

from serviceos_api.agents.result import AgentFinalOutput, parse_agent_payload, parse_agent_result


def test_plain_text_is_separate_result():
    result = parse_agent_result("  请先停止使用异常发热的设备。 ")
    assert result.text == "请先停止使用异常发热的设备。"
    assert result.ui_proposal is None and result.ui_fallback_code is None


def test_typed_output_uses_existing_ui_fallback_contract():
    result = parse_agent_payload(AgentFinalOutput(
        text="请用文字描述。", ui_proposal={"purpose": "x", "unknown": "secret"},
    ))
    assert result.text == "请用文字描述。"
    assert result.ui_proposal is None and result.ui_fallback_code == "ui_proposal_invalid"


def test_typed_output_preserves_validated_rich_reply():
    payload = AgentFinalOutput.model_validate({
        "text": "先检查电源连接。",
        "rich": {
            "schema_version": 1,
            "blocks": [{"type": "steps", "items": [
                {"title": "检查插座", "description": "确认插座供电正常。"},
            ]}],
            "quick_replies": [
                {"id": "power-ok", "label": "插座有电", "message": "我确认插座有电。"},
                {"id": "power-unknown", "label": "我不确定", "message": "我不确定插座是否有电。"},
            ],
        },
    })

    result = parse_agent_payload(payload)

    assert result.text == "先检查电源连接。"
    from serviceos_api.application.rich_reply import RichReply
    assert result.rich_reply == RichReply.model_validate(payload.rich).model_dump(mode="json")
    assert result.ui_fallback_code is None


def test_typed_output_discards_invalid_rich_reply_but_keeps_safe_text():
    result = parse_agent_payload(AgentFinalOutput.model_validate({
        "text": "先断开电源。",
        "rich": {"schema_version": 1, "blocks": [{"type": "actions"}]},
    }))

    assert result.text == "先断开电源。"
    assert result.rich_reply is None
    assert result.ui_fallback_code == "rich_reply_invalid"


@pytest.mark.parametrize("payload", [
    {"text": "", "ui_proposal": None},
    {"text": "   ", "ui_proposal": None},
    {"text": "ui_proposal 内部对象", "ui_proposal": None},
])
def test_typed_output_rejects_empty_or_internal_text(payload):
    with pytest.raises(ValueError):
        AgentFinalOutput.model_validate(payload)


def test_valid_ui_is_internal_metadata_not_text():
    payload = {"text": "请确认接口类型。", "ui_proposal": {
        "purpose": "收集接口信息", "audience": "CUSTOMER", "fallback_text": "也可用文字说明接口。",
        "component_hints": ["QuestionForm"],
    }}
    result = parse_agent_result(json.dumps(payload, ensure_ascii=False))
    assert result.text == "请确认接口类型。"
    assert result.ui_proposal == payload["ui_proposal"]
    assert "QuestionForm" not in result.text


@pytest.mark.parametrize("bad_ui", [
    {"purpose": "x", "audience": "ADMIN", "fallback_text": "fallback", "component_hints": ["QuestionForm"]},
    {"purpose": "x", "audience": "CUSTOMER", "fallback_text": "<script>x</script>", "component_hints": ["QuestionForm"]},
    {"purpose": "x", "audience": "CUSTOMER", "fallback_text": "fallback", "component_hints": ["Unknown"]},
    {"purpose": "x", "audience": "CUSTOMER", "fallback_text": "fallback", "component_hints": ["QuestionForm"], "url": "https://x"},
    {"purpose": "x" * 161, "audience": "CUSTOMER", "fallback_text": "fallback", "component_hints": ["QuestionForm"]},
])
def test_bad_ui_falls_back_to_text(bad_ui):
    result = parse_agent_result(json.dumps({"text": "请用文字描述。", "ui_proposal": bad_ui}))
    assert result.text == "请用文字描述。"
    assert result.ui_proposal is None and result.ui_fallback_code == "ui_proposal_invalid"


def test_malformed_structured_result_recovers_text_only_or_raises():
    # Truncated payloads may recover the quoted text as a fallback reply, but never
    # publish raw malformed JSON; unrecoverable input still fails closed.
    recovered = parse_agent_result('{"text": "x", "ui_proposal":')
    assert recovered.text == "x" and recovered.ui_proposal is None
    assert recovered.ui_fallback_code == "rich_result_truncated"
    with pytest.raises(ValueError, match="invalid_json"):
        parse_agent_result('{"ui_proposal": null')
    with pytest.raises(ValueError, match="invalid_json"):
        parse_agent_result('{"text":')


def proposal(**overrides):
    value = {"purpose": "确认指示灯状态", "audience": "CUSTOMER", "fallback_text": "也可用文字说明。",
             "component_hints": ["ChoiceGroup"]}
    value.update(overrides)
    return {"text": "指示灯现在是什么状态？", "ui_proposal": value}


def test_options_are_accepted_and_stay_internal_metadata():
    options = [{"label": "完全不亮", "value": "no-light"}, {"label": "常亮", "value": "steady"}]
    result = parse_agent_result(json.dumps(proposal(options=options), ensure_ascii=False))
    assert result.ui_fallback_code is None
    assert result.ui_proposal["options"] == options
    assert "完全不亮" not in result.text, "a choice is not published as reply text"


@pytest.mark.parametrize("options", [
    [],
    [{"label": "只有一个", "value": "only"}],
    [{"label": f"选项{n}", "value": f"choice-{n}"} for n in range(6)],
    [{"label": "x", "value": "Not A Slug"}],
    [{"label": "x", "value": "UPPER"}],
    [{"label": "<script>x</script>", "value": "ok"}],
    [{"label": "https://evil.example", "value": "ok"}],
    [{"label": "重复", "value": "ok"}, {"label": "重复", "value": "ok-2"}],
    [{"label": "甲", "value": "same"}, {"label": "乙", "value": "same"}],
    [{"label": "x" * 41, "value": "ok"}, {"label": "y", "value": "ok-2"}],
    [{"label": "a", "value": "ok", "extra": 1}, {"label": "b", "value": "ok-2"}],
    "not-a-list",
])
def test_unbounded_or_unsafe_options_fall_back_to_text(options):
    result = parse_agent_result(json.dumps(proposal(options=options), ensure_ascii=False))
    assert result.ui_proposal is None
    assert result.ui_fallback_code == "ui_proposal_invalid"
    assert result.text == "指示灯现在是什么状态？"


def test_fenced_structured_result_is_never_published_as_raw_json(monkeypatch):
    """Models wrap the object in a ```json fence. Publishing that fence verbatim showed the
    customer the internal proposal: purpose, hints and options included."""
    payload = proposal(options=[{"label": "完全不亮", "value": "no-light"}, {"label": "常亮", "value": "steady"}])
    for fenced in (f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```",
                   f"```\n{json.dumps(payload, ensure_ascii=False)}\n```"):
        result = parse_agent_result(fenced)
        assert result.text == payload["text"]
        assert result.ui_proposal is not None and result.ui_proposal["options"] == payload["ui_proposal"]["options"]
        for leaked in ("```", "ui_proposal", "component_hints", "fallback_text"):
            assert leaked not in result.text


def test_fenced_plain_prose_stays_prose():
    result = parse_agent_result("```\n请先断开电源。\n```")
    assert "请先断开电源。" in result.text
    assert result.ui_proposal is None and result.ui_fallback_code is None


def test_visual_hints_require_audience_and_allowlisted_source():
    chart = {"purpose": "解释加热耗电", "audience": "CUSTOMER", "fallback_text": "可阅读文字说明。",
             "component_hints": ["KnowledgeMetricChart"],
             "knowledge_source_id": "eufy-s1-pro-heating-battery-v1"}
    flow = {"purpose": "查看案例进度", "audience": "STAFF", "fallback_text": "查看案例状态。",
            "component_hints": ["CaseProcessFlow"], "case_id": "00000000-0000-0000-0000-000000000001"}
    assert parse_agent_result(json.dumps({"text": "说明如下", "ui_proposal": chart})).ui_proposal == chart
    assert parse_agent_result(json.dumps({"text": "内部查看", "ui_proposal": flow})).ui_proposal == flow

    for value in (
        {**chart, "audience": "STAFF"},
        {**chart, "knowledge_source_id": []},
        {**flow, "audience": "CUSTOMER"},
    ):
        result = parse_agent_result(json.dumps({"text": "使用文字说明。", "ui_proposal": value}))
        assert result.ui_proposal is None and result.ui_fallback_code == "ui_proposal_invalid"
