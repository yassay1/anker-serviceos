"""Deterministic application policy for customer-reported hardware hazards."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


SafetyLevel = Literal["NONE", "STOP_USE", "EMERGENCY"]
POLICY_VERSION = "hardware-hazard-v1"


@dataclass(frozen=True)
class SafetyAssessment:
    level: SafetyLevel
    rule_ids: tuple[str, ...] = ()

    @property
    def triggered(self) -> bool:
        return self.level != "NONE"

    @property
    def reply_text(self) -> str:
        if self.level == "EMERGENCY":
            return (
                "如果设备刚发生爆裂、正在冒烟或起火，请立即远离，不要触碰、移动、充电或继续排查，"
                "并联系当地消防或紧急服务；如有人受伤，请联系当地急救。到安全位置后，可通过现有入口联系人工客服。"
            )
        return (
            "如果设备出现鼓包、冒烟、焦味、漏液、明显过热或破损，请停止使用和充电，也不要继续测试；"
            "不要拆解、挤压或继续通电排查，并通过现有入口联系人工客服。"
            "单凭描述不能确认故障原因。"
        )

    def audit_value(self) -> dict:
        """Persist policy metadata without duplicating the customer's raw message."""
        return {"policy_version": POLICY_VERSION, "level": self.level, "rule_ids": list(self.rule_ids)}


_RULES: tuple[tuple[str, SafetyLevel, re.Pattern[str]], ...] = (
    ("battery_explosion", "EMERGENCY", re.compile(
        r"(?:充电宝|移动电源|锂电池|电池|设备).{0,8}(?:炸了|爆了|爆炸|爆裂)|"
        r"(?:炸了|爆了|爆炸|爆裂).{0,8}(?:充电宝|移动电源|锂电池|电池|设备)")),
    ("fire_or_ignition", "EMERGENCY", re.compile(r"起火|着火|明火|火苗|燃烧")),
    ("swelling", "STOP_USE", re.compile(r"鼓包|膨胀|鼓起来|胀起来")),
    ("smoke", "STOP_USE", re.compile(r"冒烟|烟雾")),
    ("burnt_or_odd_smell", "STOP_USE", re.compile(r"焦味|焦糊味|烧焦味|烧焦|异味")),
    ("leak", "STOP_USE", re.compile(r"漏液|渗液|液体泄漏")),
    ("overheating", "STOP_USE", re.compile(r"明显过热|异常发热|过热|发烫|烫手")),
    ("physical_damage", "STOP_USE", re.compile(r"破损|破裂|裂开|外壳裂|外壳破|电池受损")),
)
_NEGATION_PREFIX = re.compile(
    r"(?:没有|没|无|未|并未|并没有|不曾|从未|不)\s*"
    r"(?:出现|发生|发现|看到|看见|闻到|感觉到|冒出)?\s*$"
)


def _is_negated(text: str, start: int) -> bool:
    # A short local window handles direct denials without treating unrelated earlier
    # sentence text as negation. Earlier positive events (e.g. “刚才冒烟，现在没烟了”)
    # still match at their first occurrence.
    prefix = text[max(0, start - 12):start]
    return bool(_NEGATION_PREFIX.search(prefix))


def assess_hardware_hazard(text: str) -> SafetyAssessment:
    """Assess the current customer message against the hardware-hazard SOP.

    The detector is intentionally bounded and deterministic. Policy routing must not
    depend on the main Agent deciding to call a tool or mention a safety concern.
    """
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    hits: list[tuple[str, SafetyLevel]] = []
    for rule_id, level, pattern in _RULES:
        if any(not _is_negated(normalized, match.start()) for match in pattern.finditer(normalized)):
            hits.append((rule_id, level))
    if not hits:
        return SafetyAssessment("NONE")
    level: SafetyLevel = "EMERGENCY" if any(item[1] == "EMERGENCY" for item in hits) else "STOP_USE"
    return SafetyAssessment(level, tuple(rule_id for rule_id, _ in hits))
