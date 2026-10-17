import os

import pytest

from serviceos_api import settings as settings_module
from serviceos_api.settings import Settings, _llm_extra_body


def test_local_dotenv_is_loaded_only_in_development(monkeypatch, tmp_path):
    package_dir = tmp_path / "serviceos_api"
    package_dir.mkdir()
    (tmp_path / ".env").write_text("SERVICEOS_LLM_MODEL=local-only-model\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "__file__", str(package_dir / "settings.py"))
    monkeypatch.delenv("SERVICEOS_LLM_MODEL", raising=False)

    monkeypatch.setenv("SERVICEOS_ENV", "test")
    settings_module.load_environment()
    assert os.getenv("SERVICEOS_LLM_MODEL") is None

    monkeypatch.setenv("SERVICEOS_ENV", "development")
    settings_module.load_environment()
    assert os.getenv("SERVICEOS_LLM_MODEL") == "local-only-model"


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
