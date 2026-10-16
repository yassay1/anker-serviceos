"""Optional, fail-closed retrieval query rewriting.

Concept-ported from the reference project's query transformer (model/error-code
extraction, typo normalization, cross-language keyword expansion) as a single
bounded call. Any provider/parsing failure returns the original query untouched:
rewriting must never fabricate relevance, and extracted model codes only enrich
the query text -- they never widen the VERIFIED-device gating applied later.
"""

from dataclasses import dataclass
import json
import re

import httpx

from serviceos_api.integrations.http_clients import post_json
from serviceos_api.settings import Settings

REWRITE_SYSTEM = (
    "You normalize a customer query for after-sales knowledge retrieval. "
    "Output STRICT JSON only, no prose: {\"query\": string, \"models\": [string], \"keywords\": [string]}. "
    "Rules: keep the original intent; extract product model codes (e.g. T2352, E25, X10 Pro, T8D04) "
    "and error codes into models; fix obvious typos; if the query is Chinese, add English keywords "
    "matching likely English manual wording into keywords; never invent facts or answers."
)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


@dataclass(frozen=True)
class RewriteResult:
    query: str
    applied: bool
    reason: str = ""


class QueryRewriter:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    def rewrite(self, query: str) -> RewriteResult:
        if not self.settings.llm_configured:
            return RewriteResult(query, False, "provider_unconfigured")
        try:
            response = post_json(
                f"{self.settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                payload={
                    "model": self.settings.fast_or_llm_model,
                    "temperature": 0,
                    "max_completion_tokens": 300,
                    "messages": [
                        {"role": "system", "content": REWRITE_SYSTEM},
                        {"role": "user", "content": query[:2000]},
                    ],
                },
                timeout=self.settings.llm_timeout_seconds,
                transport=self._transport,
            )
            response.raise_for_status()
            payload = response.json()
            content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            parsed = json.loads(_FENCE.sub("", content.strip()))
            if not isinstance(parsed, dict):
                raise ValueError("rewrite_shape")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return RewriteResult(query, False, "rewrite_unavailable")
        parts = [query.strip()]
        for key in ("keywords", "models"):
            values = parsed.get(key)
            if isinstance(values, list):
                parts.extend(str(value).strip() for value in values
                             if isinstance(value, (str, int)) and str(value).strip())
        effective = " ".join(dict.fromkeys(parts))[:600]
        return RewriteResult(effective, True)
