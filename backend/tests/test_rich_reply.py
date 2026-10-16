from serviceos_api.application.rich_reply import RichReply, safety_rich_reply
from serviceos_api.application.safety_policy import assess_hardware_hazard


def test_server_safety_projection_contains_only_safety_and_assistance():
    assessment = assess_hardware_hazard("我的充电宝炸了")
    projected = safety_rich_reply(assessment)

    assert projected["schema_version"] == 1
    assert [block["type"] for block in projected["blocks"]] == ["alert", "actions"]
    assert projected["blocks"][0]["status_code"] == "POLICY_SAFETY_STOP"
    assert projected["blocks"][0]["text"] == assessment.reply_text
    assert projected["blocks"][1]["action"] == "request_assistance"
    assert projected["quick_replies"] == []


def test_rich_reply_model_contract_still_accepts_normal_steps():
    reply = RichReply.model_validate({
        "schema_version": 1,
        "blocks": [{"type": "steps", "items": [{"title": "确认", "description": "查看设备状态"}]}],
        "quick_replies": [],
    })
    assert reply.blocks[0].type == "steps"
