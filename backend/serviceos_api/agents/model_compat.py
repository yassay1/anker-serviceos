"""Provider request options shared by the main and specialist Agent runtimes."""

from urllib.parse import urlsplit

from serviceos_api.settings import Settings


def model_provider_options(settings: Settings) -> dict:
    extra_body = dict(settings.llm_extra_body)
    host = urlsplit(settings.llm_base_url).hostname
    if host == "api.deepseek.com":
        # DeepSeek defaults to thinking mode, which rejects ToolStrategy's required
        # tool_choice. Other OpenAI-compatible providers can provide request options
        # through SERVICEOS_LLM_EXTRA_BODY_JSON.
        extra_body.setdefault("thinking", {"type": "disabled"})
    if host == "api.xiaomimimo.com" and settings.llm_model.startswith("mimo-"):
        # MiMo enables reasoning by default; reserve the completion budget for the
        # customer-visible reply while keeping the same tool contract.
        extra_body.setdefault("thinking", {"type": "disabled"})
    return {"extra_body": extra_body} if extra_body else {}
