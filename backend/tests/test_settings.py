import pytest

from serviceos_api.settings import Settings, _llm_extra_body


def test_provider_extra_body_is_optional_json_object():
    assert _llm_extra_body("") == {}
    assert _llm_extra_body('{"provider_option":true}') == {"provider_option": True}


@pytest.mark.parametrize("value", ["not-json", "[]", "null", '"text"'])
def test_provider_extra_body_rejects_non_object_configuration(value):
    with pytest.raises(ValueError, match="SERVICEOS_LLM_EXTRA_BODY_JSON"):
        _llm_extra_body(value)


def test_provider_extra_body_is_hidden_from_settings_repr():
    settings = Settings(llm_extra_body={"token": "private"})
    assert "private" not in repr(settings)
