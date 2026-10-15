import json

from serviceos_api.agents.runtime import _safe_json
from serviceos_api.application.agent_services import _search_tokens, estimate_tokens


def test_context_estimator_accounts_for_cjk_and_ascii_tokens():
    assert estimate_tokens("充电") == 2
    assert estimate_tokens("charging cable") == 4


def test_manual_search_tokens_match_chinese_issue_terms():
    assert _search_tokens("手机不充电") & _search_tokens("不充电排查")


def test_safe_json_preserves_complete_large_context():
    context = {"current_problem": "问题" * 12000, "priority": "must_keep",
               "context_memory": {"storage_only": True}}
    encoded = _safe_json(context)
    decoded = json.loads(encoded)
    assert decoded == {"current_problem": context["current_problem"], "priority": "must_keep"}
