from serviceos_api.agents.model_compat import model_provider_options as _provider_request_options
from serviceos_api.settings import Settings


def test_official_mimo_uses_responsive_chat_mode():
    settings = Settings(llm_model="mimo-v2.6-pro", llm_base_url="https://api.xiaomimimo.com/v1")
    assert _provider_request_options(settings) == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_other_providers_keep_their_existing_parameters():
    for model, url in [("deepseek-v4-pro", "https://example.com/v1"),
                       ("mimo-v2.6-pro", "https://api.xiaomimimo.com.example.com/v1")]:
        assert _provider_request_options(Settings(llm_model=model, llm_base_url=url)) == {}
