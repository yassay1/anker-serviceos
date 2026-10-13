import json

import pytest

from serviceos_api.agents.result import parse_agent_result


def test_plain_text_is_separate_result():
    result = parse_agent_result("  请先停止使用异常发热的设备。 ")
    assert result.text == "请先停止使用异常发热的设备。"
    assert result.ui_proposal is None and result.ui_fallback_code is None


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


def test_malformed_structured_result_cannot_be_published_raw():
    with pytest.raises(ValueError, match="invalid_json"):
        parse_agent_result('{"text": "x", "ui_proposal":')
