from serviceos_api.application.rich_reply import RISK, SAFETY_TEXT, RichReply, _safety_reply


def test_safety_reply_discards_model_narrative_and_neutralizes_image_caption():
    reply = RichReply.model_validate({
        "schema_version": 1,
        "blocks": [
            {"type": "summary", "text": "继续充电并重新开机。"},
            {"type": "steps", "items": [{"title": "排查", "description": "保持通电。"}]},
            {"type": "alert", "text": "可以继续使用。"},
            {"type": "image_focus", "case_id": "11111111-1111-4111-8111-111111111111",
             "evidence_id": "22222222-2222-4222-8222-222222222222", "text": "注意这里发烫，继续运行。",
             "focus": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}},
            {"type": "status", "case_id": "11111111-1111-4111-8111-111111111111", "text": "模型写的状态"},
        ],
        "quick_replies": [
            {"id": "keep-using", "label": "继续使用", "message": "我继续使用设备。"},
            {"id": "keep-charging", "label": "继续充电", "message": "我继续给设备充电。"},
        ],
    })

    safe = _safety_reply(reply)

    assert [block.type for block in safe.blocks] == ["alert", "image", "status"]
    assert safe.blocks[0].title == "先停止使用设备"
    assert safe.blocks[0].text == SAFETY_TEXT
    assert safe.blocks[0].severity == "danger"
    assert safe.blocks[0].status_code == "POLICY_SAFETY_STOP"
    assert safe.blocks[1].title == "用户提供的图片"
    assert safe.blocks[1].text == "已收到设备图片；无法据此确认故障原因。请先遵循安全提示。"
    assert safe.blocks[1].focus is None
    assert safe.quick_replies == []
def test_risk_filter_matches_overheating_but_respects_negation():
    assert RISK.search('设备明显过热')
    assert RISK.search('设备过热')
    assert not RISK.search('设备不过热')
    assert not RISK.search('设备没有过热')
