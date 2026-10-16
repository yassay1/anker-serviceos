"""Small, deterministic controls for repeated Agent tool calls and budget exits."""

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.messages import AIMessage, ToolMessage


MAIN_MODEL_RUN_LIMIT = 6
MAIN_MODEL_THREAD_LIMIT = 8
MAIN_TOOL_RUN_LIMIT = 12
MAIN_TOOL_THREAD_LIMIT = 18
MAIN_LOOKUP_RUN_LIMIT = 4
MAIN_LOOKUP_THREAD_LIMIT = 6
MAIN_RECURSION_LIMIT = 40

SPECIALIST_MODEL_RUN_LIMIT = 3
SPECIALIST_MODEL_THREAD_LIMIT = 4
SPECIALIST_TOOL_RUN_LIMIT = 6
SPECIALIST_TOOL_THREAD_LIMIT = 8
SPECIALIST_LOOKUP_RUN_LIMIT = 4
SPECIALIST_LOOKUP_THREAD_LIMIT = 6
SPECIALIST_RECURSION_LIMIT = 24

def _messages(state: Any) -> list[Any]:
    if isinstance(state, dict):
        value = state.get("messages", [])
    else:
        value = getattr(state, "messages", [])
    return value if isinstance(value, list) else []


def _query_key(call: dict[str, Any]) -> str | None:
    if call.get("name") != "lookup_manual":
        return None
    args = call.get("args")
    query = args.get("query") if isinstance(args, dict) else None
    if not isinstance(query, str) or not query.strip():
        return None
    return " ".join(query.split()).casefold()


@wrap_tool_call
def suppress_repeated_manual_lookup(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage],
) -> ToolMessage:
    """Reuse the first successful exact lookup in a thread instead of searching again.

    Only an identical query with a successful prior result is suppressed. A failed or
    interrupted lookup can run again, and a changed query remains eligible. No raw
    query is persisted by this middleware.
    """
    call = request.tool_call
    query_key = _query_key(call)
    if query_key is None:
        return handler(request)

    messages = _messages(request.state)
    result_status = {
        message.tool_call_id: getattr(message, "status", "success")
        for message in messages
        if isinstance(message, ToolMessage)
    }
    current_id = call.get("id")
    current_message_index = None
    current_call_index = None
    for message_index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue
        for call_index, candidate in enumerate(message.tool_calls or []):
            if candidate.get("id") == current_id:
                current_message_index = message_index
                current_call_index = call_index
                break
        if current_message_index is not None:
            break

    if current_message_index is not None and current_call_index is not None:
        prior_same_success = any(
            isinstance(message, AIMessage)
            and _query_key(previous) == query_key
            and previous.get("id") in result_status
            and result_status.get(previous.get("id")) != "error"
            for message in messages[:current_message_index]
            if isinstance(message, AIMessage)
            for previous in (message.tool_calls or [])
        )
        same_batch_duplicate = any(
            _query_key(previous) == query_key
            for previous in messages[current_message_index].tool_calls[:current_call_index]
        )
        if same_batch_duplicate:
            return ToolMessage(
                content=("本次模型响应已包含相同的手册检索调用；该重复调用已跳过。"
                         "请使用首个调用的结果继续，不要重复检索。"),
                tool_call_id=current_id,
                name="lookup_manual",
            )
        if prior_same_success:
            return ToolMessage(
                content=("完全相同的手册检索已在本次执行中成功完成；没有重新检索。"
                         "请使用已有检索结果收尾，或询问客户缺失的关键信息。"),
                tool_call_id=current_id,
                name="lookup_manual",
            )
    return handler(request)


def budget_exhaustion_fallback(context: dict[str, Any]) -> str:
    """Safe, deterministic customer-facing fallback when an execution cap is reached."""
    verified = any(
        isinstance(device, dict)
        and device.get("identity_status") == "VERIFIED"
        and device.get("model")
        for device in context.get("linked_devices", [])
    )
    if verified:
        return ("为了避免给您不准确的处理建议，我还需要更多故障信息。"
                "请告诉我问题发生时正在进行什么操作，以及设备指示灯或提示信息的具体表现。")
    return ("为了避免把不同型号的资料用错，我需要先确认设备型号和故障表现。"
            "请提供设备准确型号（可查看 App 设备信息或设备标签），以及问题发生时的具体情况。")
