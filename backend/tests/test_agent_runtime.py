from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from serviceos_api.agents import diagnostic, runtime
from serviceos_api.agents.model_compat import model_provider_options
from serviceos_api.agents.result import AgentFinalOutput
from serviceos_api.application.diagnostic_contracts import DiagnosticResult, DiagnosticTaskInput
from serviceos_api.settings import Settings


def install_fake_checkpointer(monkeypatch):
    module = ModuleType("langgraph.checkpoint.postgres")
    module.PostgresSaver = lambda connection: object()
    monkeypatch.setitem(__import__("sys").modules, "langgraph.checkpoint.postgres", module)

    @contextmanager
    def connection():
        yield object()

    monkeypatch.setattr(runtime, "checkpoint_connection", connection)
    monkeypatch.setattr(diagnostic, "checkpoint_connection", connection)


def test_service_agent_keeps_diagnostic_as_an_optional_manager_tool(monkeypatch):
    captured = {}

    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={}, next=[])

        def invoke(self, _state, config):
            captured["config"] = config
            return {"structured_response": AgentFinalOutput(text="已有资料足够回答。"), "messages": []}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return FakeGraph()

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **kwargs: captured.setdefault("model_kwargs", kwargs) or object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "create_agent", fake_create_agent)
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://api.deepseek.com")

    result, _ = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
        message_id=uuid4(), context={"context_budget": {}}, current_text="如何使用？",
    )

    assert result.text == "已有资料足够回答。"
    assert {tool.name for tool in captured["tools"]} == {
        "lookup_manual", "query_order_warranty", "check_dealer_authorization", "get_case_stage",
        "resolve_policy", "load_skill", "request_missing_evidence", "propose_action",
        "request_mock_service_action",
        "delegate_diagnostic", "get_service_progress",
    }
    action_tool = next(tool for tool in captured["tools"] if tool.name == "request_mock_service_action")
    action_schema = action_tool.args_schema.model_json_schema()["properties"]
    assert set(action_schema) == {"remedy_type", "reason"}
    remedy_schema = action_schema["remedy_type"]
    assert remedy_schema["enum"] == ["REPAIR", "RESHIP", "REFER_SELLER", "DECLINE"]
    assert captured["config"]["recursion_limit"] == runtime.MAIN_RECURSION_LIMIT
    assert captured["config"]["max_concurrency"] == 1
    assert any(getattr(middleware, "run_limit", None) == 6 for middleware in captured["middleware"])
    assert any(getattr(middleware, "run_limit", None) == 12 for middleware in captured["middleware"])
    assert any(getattr(middleware, "tool_name", None) == "lookup_manual"
               and getattr(middleware, "run_limit", None) == runtime.MAIN_LOOKUP_RUN_LIMIT
               and getattr(middleware, "thread_limit", None) == runtime.MAIN_LOOKUP_THREAD_LIMIT
               for middleware in captured["middleware"])
    assert any(getattr(middleware, "thread_limit", None) == runtime.MAIN_MODEL_THREAD_LIMIT
               for middleware in captured["middleware"])
    assert captured["response_format"].schema is AgentFinalOutput
    assert captured["model_kwargs"]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_service_agent_reuses_structured_checkpoint_without_model_call(monkeypatch):
    expected = AgentFinalOutput(text="已保存的答复。")
    captured = {}

    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={"structured_response": expected, "messages": []}, next=[])

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("a completed structured checkpoint must be reused")

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph())
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="http://model")

    result, _ = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
        message_id=uuid4(), context={"context_budget": {}}, current_text="继续",
    )
    assert result.text == "已保存的答复。"


def test_service_agent_returns_safe_question_when_execution_budget_is_exhausted(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={"messages": []}, next=[])

        def invoke(self, *_args, **_kwargs):
            raise runtime.GraphRecursionError("recursion_limit")

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph())
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="http://model")

    result, stats = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
        message_id=uuid4(), context={"context_budget": {}}, current_text="设备没反应",
    )

    assert result.text.startswith("为了避免把不同型号的资料用错")
    assert stats["execution_termination"] == "GraphRecursionError"


def test_openai_compatible_provider_options_are_configurable():
    deepseek = model_provider_options(Settings(
        environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://api.deepseek.com",
    ))
    generic = model_provider_options(Settings(
        environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://provider.example/v1",
        llm_extra_body={"thinking": {"type": "disabled"}, "provider_flag": True},
    ))
    assert deepseek == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert generic == {"extra_body": {"thinking": {"type": "disabled"}, "provider_flag": True}}


def test_new_typed_run_never_falls_back_to_unstructured_model_text(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={}, next=[])

        def invoke(self, state, config=None):
            user_message = state["messages"][-1]
            assert user_message.additional_kwargs["serviceos_output_contract"] == "typed_v1"
            return {"messages": [AIMessage(content="unstructured model text")]}

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph())
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://provider.example")

    with pytest.raises(runtime.AgentOutputInvalidError):
        runtime.AgentRuntime(settings).invoke(
            tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
            message_id=uuid4(), context={"context_budget": {}}, current_text="请回复。",
        )


def test_legacy_checkpoint_output_is_accepted_only_when_valid(monkeypatch):
    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://provider.example")
    message_id = uuid4()
    legacy_user = HumanMessage(content="legacy input", additional_kwargs={"serviceos_message_id": str(message_id)})

    class FakeGraph:
        def __init__(self, output):
            self.output = output

        def get_state(self, _config):
            return SimpleNamespace(values={"messages": [legacy_user, AIMessage(content=self.output)]}, next=[])

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("completed legacy checkpoints are read, not rerun")

    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph('{"text":"旧版已保存答复。"}'))
    result, _ = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
        message_id=message_id, context={"context_budget": {}}, current_text="继续",
    )
    assert result.text == "旧版已保存答复。"

    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph('{"text":"旧版坏答复":'))
    result, _ = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
        message_id=message_id, context={"context_budget": {}}, current_text="继续",
    )
    assert result.text == "旧版坏答复" and result.ui_fallback_code == "rich_result_truncated"

    monkeypatch.setattr(runtime, "create_agent", lambda **_kwargs: FakeGraph('{"text::'))
    with pytest.raises(runtime.AgentOutputInvalidError):
        runtime.AgentRuntime(settings).invoke(
            tenant_id=uuid4(), conversation_id=uuid4(), run_id=uuid4(), lease_token=uuid4(),
            message_id=message_id, context={"context_budget": {}}, current_text="继续",
        )


def test_diagnostic_agent_exposes_only_bounded_read_only_tools(monkeypatch):
    captured = {}
    task = DiagnosticTaskInput(task_id=uuid4(), conversation_id=uuid4(), goal="分析供电问题")
    expected = DiagnosticResult(
        task_id=task.task_id, assessment="可能是供电连接问题", next_step={"kind": "ASK_CUSTOMER", "summary": "确认充电器", "question": {"prompt": "充电器指示灯是否亮起？"}},
        staff_summary="假设，尚未核验。",
    )

    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={}, next=[])

        def invoke(self, _state, config):
            captured["config"] = config
            return {"structured_response": expected, "messages": []}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return FakeGraph()

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(diagnostic, "ChatOpenAI", lambda **kwargs: captured.setdefault("diagnostic_model_kwargs", kwargs) or object())
    monkeypatch.setattr(diagnostic, "create_agent", fake_create_agent)
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="https://api.deepseek.com")

    result, _ = diagnostic.DiagnosticAgentRuntime(settings).invoke(
        task=task, tenant_id=uuid4(), conversation_id=task.conversation_id, parent_run_id=uuid4(),
        lease_token=uuid4(), message_id=uuid4(), checkpoint_thread_id="diagnostic:test",
        specialist_run_id=uuid4(),
    )

    assert result == expected
    assert {tool.name for tool in captured["tools"]} == {"lookup_manual", "load_skill"}
    assert captured["response_format"].schema is DiagnosticResult
    assert captured["diagnostic_model_kwargs"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured["config"]["recursion_limit"] == diagnostic.SPECIALIST_RECURSION_LIMIT
    assert captured["config"]["max_concurrency"] == 1
    assert any(getattr(middleware, "run_limit", None) == 3 for middleware in captured["middleware"])
    assert any(getattr(middleware, "run_limit", None) == 4 for middleware in captured["middleware"])
    assert any(getattr(middleware, "run_limit", None) == diagnostic.SPECIALIST_TOOL_RUN_LIMIT
               and getattr(middleware, "thread_limit", None) == diagnostic.SPECIALIST_TOOL_THREAD_LIMIT
               for middleware in captured["middleware"])
    assert any(getattr(middleware, "tool_name", None) == "lookup_manual"
               and getattr(middleware, "run_limit", None) == diagnostic.SPECIALIST_LOOKUP_RUN_LIMIT
               and getattr(middleware, "thread_limit", None) == diagnostic.SPECIALIST_LOOKUP_THREAD_LIMIT
               for middleware in captured["middleware"])


def test_customer_answer_resumes_persisted_task_before_manager_reply(monkeypatch):
    captured = {}
    task_id, answer_id, specialist_id = uuid4(), uuid4(), uuid4()
    task_input = DiagnosticTaskInput(task_id=task_id, conversation_id=uuid4(), goal="排查供电问题")
    answer = SimpleNamespace(answer="指示灯亮起")
    specialist = SimpleNamespace(id=specialist_id, checkpoint_thread_id=f"diagnostic:{task_id}:{answer_id}")
    diagnostic_result = DiagnosticResult(task_id=task_id, assessment="仍需核对线材", next_step={"kind": "NO_ACTION", "summary": "请继续确认"}, staff_summary="待核验。")

    class FakeService:
        def resume_diagnostic(self, actual_task_id, actual_answer_id):
            assert (actual_task_id, actual_answer_id) == (task_id, answer_id)
            return SimpleNamespace(id=task_id), specialist, task_input, answer, None

        def complete_diagnostic(self, actual_task_id, actual_specialist_id, result, *_):
            assert (actual_task_id, actual_specialist_id) == (task_id, specialist_id)
            assert result == diagnostic_result
            return {"task_id": str(task_id), "assessment": result.assessment, "certainty": "HYPOTHESIS"}

        def fail_diagnostic(self, *_):
            raise AssertionError("success path must not mark the task failed")

    @contextmanager
    def tool_service(*_):
        yield FakeService()

    class FakeGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={}, next=[])

        def invoke(self, state, config):
            captured["manager_input"] = state["messages"][-1].content
            return {"structured_response": AgentFinalOutput(text="我已收到补充信息。"), "messages": []}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return FakeGraph()

    install_fake_checkpointer(monkeypatch)
    monkeypatch.setattr(runtime, "_tool_service", tool_service)
    monkeypatch.setattr(runtime, "ChatOpenAI", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "SummarizationMiddleware", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "create_agent", fake_create_agent)
    monkeypatch.setattr(diagnostic, "DiagnosticAgentRuntime", lambda _settings: SimpleNamespace(invoke=lambda **kwargs: (
        captured.setdefault("resume_args", kwargs) and diagnostic_result,
        {"manual_source_refs": [], "input_tokens": 4},
    )))
    settings = Settings(environment="test", llm_model="model", llm_api_key="test", llm_base_url="http://model")

    result, _ = runtime.AgentRuntime(settings).invoke(
        tenant_id=uuid4(), conversation_id=task_input.conversation_id, run_id=uuid4(), lease_token=uuid4(),
        message_id=uuid4(), context={"diagnostic_resume": {"task_id": str(task_id), "answer_id": str(answer_id)}},
        current_text="灯亮起",
    )

    assert result.text == "我已收到补充信息。"
    assert captured["resume_args"]["answer_text"] == "指示灯亮起"
    assert "diagnostic_resume_result" not in captured["manager_input"]
    assert "resumed_diagnostic_result" in captured["manager_input"]
