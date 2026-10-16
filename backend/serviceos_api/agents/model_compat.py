"""Provider request options shared by the main and specialist Agent runtimes."""

from urllib.parse import urlsplit

from serviceos_api.settings import Settings


def model_provider_options(settings: Settings) -> dict:
    extra_body = dict(settings.llm_extra_body)
    hostname = urlsplit(settings.llm_base_url).hostname
    if (hostname == "api.deepseek.com"
            or (hostname == "api.xiaomimimo.com" and settings.llm_model.startswith("mimo-"))):
        # DeepSeek and MiMo default to thinking mode, which conflicts with the
        # interactive structured-output request. Explicit configured options win.
        extra_body.setdefault("thinking", {"type": "disabled"})
    return {"extra_body": extra_body} if extra_body else {}
