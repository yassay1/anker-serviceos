from serviceos_api.application.safety_policy import assess_hardware_hazard


def test_explosion_and_fire_are_emergency_hazards():
    assessment = assess_hardware_hazard("我的充电宝炸了")
    assert assessment.level == "EMERGENCY"
    assert "battery_explosion" in assessment.rule_ids
    assert "当地消防或紧急服务" in assessment.reply_text

    fire = assess_hardware_hazard("充电宝起火了")
    assert fire.level == "EMERGENCY"
    assert "fire_or_ignition" in fire.rule_ids


def test_sop_hazard_phrases_trigger_stop_use():
    for phrase in ("电池鼓包", "设备冒烟", "有焦味", "电池过热", "外壳破损", "电池漏液"):
        assessment = assess_hardware_hazard(phrase)
        assert assessment.level == "STOP_USE", phrase
        assert "停止使用和充电" in assessment.reply_text
        assert "不要继续测试" in assessment.reply_text


def test_direct_negation_does_not_trigger_but_past_hazard_does():
    assert not assess_hardware_hazard("设备没有冒烟，也没有过热").triggered
    assert not assess_hardware_hazard("没有焦味，没有鼓包").triggered
    assert assess_hardware_hazard("刚才冒烟了，现在没烟了").level == "STOP_USE"


def test_audit_value_contains_policy_metadata_not_source_text():
    assessment = assess_hardware_hazard("我的充电宝炸了")
    audit = assessment.audit_value()
    assert audit == {
        "policy_version": "hardware-hazard-v1",
        "level": "EMERGENCY",
        "rule_ids": ["battery_explosion"],
    }
    assert "我的充电宝炸了" not in str(audit)
