from copy import deepcopy
from uuid import uuid4

import pytest

from serviceos_api.application.errors import ServiceError
from serviceos_api.application.ui_catalog import validate_components


def component(conversation_id):
    return {"id": "request-assistance", "type": "ActionBar",
            "props": {"title": "人工协助", "body": "创建人工任务"},
            "data_source": {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation_id),
                            "resource_version": 1, "binding": "assistance"},
            "actions": [{"action_id": "request-human-assistance", "intent": "REQUEST_ASSISTANCE",
                         "input_schema_ref": "serviceos://ui-inputs/assistance-request/v1"}],
            "children": []}


def test_catalog_rejects_unknown_code_and_unauthorized_source():
    conversation_id = uuid4()
    allowed = {("CONVERSATION_VIEW", conversation_id): 1}
    valid = component(conversation_id)
    assert validate_components([valid], "CUSTOMER", allowed)[0]["type"] == "ActionBar"
    unknown = deepcopy(valid)
    unknown["type"] = "RemoteHTML"
    with pytest.raises(ServiceError):
        validate_components([unknown], "CUSTOMER", allowed)
    code = deepcopy(valid)
    code["props"]["body"] = "<script>alert(1)</script>"
    with pytest.raises(ServiceError):
        validate_components([code], "CUSTOMER", allowed)
    source = deepcopy(valid)
    source["data_source"]["resource_id"] = str(uuid4())
    with pytest.raises(ServiceError):
        validate_components([source], "CUSTOMER", allowed)
    stale = deepcopy(valid)
    stale["data_source"]["resource_version"] = 2
    with pytest.raises(ServiceError):
        validate_components([stale], "CUSTOMER", allowed)
