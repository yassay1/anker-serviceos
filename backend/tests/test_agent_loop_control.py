from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from serviceos_api.agents.loop_control import suppress_repeated_manual_lookup


def _request(messages, *, query="anker camera offline", call_id="current", call_index=0):
    call = {"name": "lookup_manual", "args": {"query": query}, "id": call_id}
    current = AIMessage(content="", tool_calls=[call])
    messages.append(current)
    request = SimpleNamespace(
        tool_call=call,
        state={"messages": messages},
    )
    return request


def test_successful_exact_lookup_is_skipped_but_failed_lookup_can_retry():
    previous = AIMessage(content="", tool_calls=[{
        "name": "lookup_manual", "args": {"query": "Anker   Camera Offline"}, "id": "old",
    }])
    successful = ToolMessage(content="manual evidence", tool_call_id="old", name="lookup_manual")
    called = []

    result = suppress_repeated_manual_lookup.wrap_tool_call(
        _request([previous, successful]), lambda request: called.append(request) or None,
    )
    assert not called
    assert "已在本次执行中成功完成" in result.content

    failed = ToolMessage(content="temporary error", tool_call_id="old", name="lookup_manual", status="error")
    called.clear()
    result = suppress_repeated_manual_lookup.wrap_tool_call(
        _request([previous, failed]), lambda request: called.append(request) or "retried",
    )
    assert called
    assert result == "retried"


def test_changed_lookup_and_same_response_duplicate_are_handled_without_extra_search():
    previous = AIMessage(content="", tool_calls=[{
        "name": "lookup_manual", "args": {"query": "camera offline"}, "id": "old",
    }])
    successful = ToolMessage(content="manual evidence", tool_call_id="old", name="lookup_manual")
    changed = _request([previous, successful], query="camera blinking red")
    called = []
    result = suppress_repeated_manual_lookup.wrap_tool_call(
        changed, lambda request: called.append(request) or "new search",
    )
    assert called
    assert result == "new search"

    first = {"name": "lookup_manual", "args": {"query": "camera offline"}, "id": "first"}
    second = {"name": "lookup_manual", "args": {"query": " camera  offline "}, "id": "second"}
    request = SimpleNamespace(tool_call=second, state={"messages": [AIMessage(content="", tool_calls=[first, second])]})
    called.clear()
    result = suppress_repeated_manual_lookup.wrap_tool_call(
        request, lambda item: called.append(item) or None,
    )
    assert not called
    assert "相同的手册检索调用" in result.content
