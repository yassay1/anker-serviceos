from types import SimpleNamespace
from uuid import uuid4

from serviceos_api.application.ui_visualizations import case_process_flow, knowledge_metric_chart


def test_curated_metric_is_bound_to_verified_model_and_published_source():
    assert knowledge_metric_chart("eufy-s1-pro-heating-battery-v1", {"T8D04"})["points"] == [
        {"label": "5 分钟", "value": 10.0},
        {"label": "10 分钟", "value": 20.0},
        {"label": "15 分钟", "value": 30.0},
    ]
    assert knowledge_metric_chart("unknown", {"T8D04"}) is None
    assert knowledge_metric_chart("eufy-s1-pro-heating-battery-v1", {"T8D04-OTHER"}) is None


def test_curated_metric_is_suppressed_if_publication_or_values_change(tmp_path, monkeypatch):
    from serviceos_api.application import ui_visualizations

    original = ui_visualizations.HEATING_KNOWLEDGE_PATH.read_text(encoding="utf-8")
    source = tmp_path / "metric.md"
    monkeypatch.setattr(ui_visualizations, "HEATING_KNOWLEDGE_PATH", source)
    for changed in (
        original.replace("Publication status: Published", "Publication status: Draft"),
        original.replace("Consumer visibility: Visible", "Consumer visibility: Internal"),
        original.replace("Point: 10 minutes = 20 percent", "Point: 10 minutes = 99 percent"),
    ):
        source.write_text(changed, encoding="utf-8")
        assert knowledge_metric_chart("eufy-s1-pro-heating-battery-v1", {"T8D04"}) is None


def test_curated_metric_accepts_windows_crlf_source(tmp_path, monkeypatch):
    from serviceos_api.application import ui_visualizations

    content = ui_visualizations.HEATING_KNOWLEDGE_PATH.read_text(encoding="utf-8")
    source = tmp_path / "metric.md"
    monkeypatch.setattr(ui_visualizations, "HEATING_KNOWLEDGE_PATH", source)
    source.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))

    chart = knowledge_metric_chart("eufy-s1-pro-heating-battery-v1", {"T8D04"})

    assert chart is not None
    assert [point["value"] for point in chart["points"]] == [10.0, 20.0, 30.0]


def test_case_flow_projects_real_states_without_claiming_unverified_completion():
    case = SimpleNamespace(id=uuid4(), version=4, status="WAITING_CUSTOMER")
    task = SimpleNamespace(id=uuid4(), version=2, status="OPEN")
    action = SimpleNamespace(status="WAITING_APPROVAL")
    verification = SimpleNamespace(observed_result="UNCERTAIN", decision="PENDING")

    flow = case_process_flow(case, task, action, verification)
    states = {node["id"]: node["status"] for node in flow["nodes"]}
    assert states == {"case": "WAITING", "human-task": "WAITING", "service-action": "WAITING",
                      "verification": "WAITING"}
    assert flow["nodes"][0]["resource_id"] == case.id
    assert flow["nodes"][1]["resource_id"] == task.id
    assert {tuple(edge.values()) for edge in flow["edges"]} == {
        ("case", "human-task"), ("case", "service-action"), ("service-action", "verification"),
    }

    resolved = case_process_flow(SimpleNamespace(id=case.id, version=5, status="RESOLVED"))
    assert resolved["nodes"][0]["status"] == "COMPLETED"
    assert "核验" not in resolved["nodes"][0]["detail"]
