"""Keep draft routes separate from the exported application contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[2] / "contracts/proposed/v1/sync_implemented.py"
SPEC = importlib.util.spec_from_file_location("proposed_sync", SCRIPT)
assert SPEC and SPEC.loader
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def sources(tmp_path, monkeypatch, planned):
    actual = {
        "openapi": "3.1.0",
        "info": {"title": "Actual", "version": "1"},
        "paths": {"/existing": {"get": {"operationId": "read_existing", "responses": {"200": {"description": "OK"}}}}},
        "components": {"schemas": {"Existing": {"type": "object"}}},
    }
    actual_path = tmp_path / "actual.json"
    planned_path = tmp_path / "planned.yaml"
    actual_path.write_text(json.dumps(actual), encoding="utf-8")
    planned_path.write_text(yaml.safe_dump(planned), encoding="utf-8")
    monkeypatch.setattr(sync, "ACTUAL", actual_path)
    monkeypatch.setattr(sync, "PLANNED", planned_path)


def test_implemented_operation_is_copied_without_changing_actual(tmp_path, monkeypatch):
    sources(tmp_path, monkeypatch, {"paths": {"/future": {"post": {
        "operationId": "create_future", "x-serviceos-status": "planned",
        "responses": {"202": {"description": "Accepted"}},
    }}}})

    proposal = sync.build()

    assert proposal["paths"]["/existing"]["get"]["x-serviceos-status"] == "implemented"
    assert proposal["paths"]["/future"]["post"]["x-serviceos-status"] == "planned"
    assert "x-serviceos-status" not in json.loads(sync.ACTUAL.read_text())["paths"]["/existing"]["get"]


@pytest.mark.parametrize("planned", [
    {"paths": {"/future": {"post": {"operationId": "create_future"}}}},
    {"paths": {"/future": {"post": {"operationId": "create_future", "x-serviceos-status": "implemented"}}}},
    {"paths": {"/existing": {"get": {"operationId": "duplicate", "x-serviceos-status": "planned"}}}},
    {"components": {"schemas": {"Unmarked": {"type": "object"}}}},
])
def test_invalid_planned_source_is_rejected(tmp_path, monkeypatch, planned):
    sources(tmp_path, monkeypatch, planned)

    with pytest.raises(ValueError):
        sync.build()
