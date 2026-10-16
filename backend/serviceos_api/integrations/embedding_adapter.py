"""Embedding adapters: OpenAI-compatible /embeddings and DashScope multimodal-embedding.

Explicit configuration only: without model, base URL and API key the adapter is
unavailable and callers must degrade to keyword-only retrieval. Vectors are never
fabricated locally, and neither queries nor responses are logged. The DashScope
multimodal protocol (qwen3-vl-embedding) also accepts image contents, which keeps
the door open for future image-evidence retrieval; today only text is embedded.
"""

import httpx

from serviceos_api.integrations.http_clients import post_json
from serviceos_api.settings import Settings

DASHSCOPE_MULTIMODAL_PATH = "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"


class EmbeddingUnavailable(RuntimeError):
    """Provider is not configured or returned an unusable response."""


class EmbeddingAdapter:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self.settings.embedding_configured

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_contents([{"text": value} for value in texts])

    def embed_contents(self, contents: list[dict]) -> list[list[float]]:
        """Embed text and/or image contents; one vector per content item.

        ``openai_compatible`` providers only accept text items; callers must not
        pass image items unless ``supports_image`` is true.
        """
        if not self.configured:
            raise EmbeddingUnavailable("embedding_provider_unconfigured")
        if not contents:
            return []
        if self.settings.embedding_provider == "dashscope_multimodal":
            payload_input = {"contents": contents}
            url = f"{self.settings.embedding_base_url}{DASHSCOPE_MULTIMODAL_PATH}"
        else:
            texts = [item.get("text", "") for item in contents if isinstance(item.get("text"), str)]
            if len(texts) != len(contents):
                raise EmbeddingUnavailable("provider_cannot_embed_image")
            payload_input = texts
            url = f"{self.settings.embedding_base_url}/embeddings"
        try:
            if self.settings.embedding_provider == "dashscope_multimodal":
                response = post_json(
                    url,
                    headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
                    payload={
                        "model": self.settings.embedding_model,
                        "input": payload_input,
                        "parameters": {"dimension": self.settings.embedding_dimensions},
                    },
                    timeout=self.settings.embedding_timeout_seconds,
                    transport=self._transport,
                )
            else:
                response = post_json(
                    url,
                    headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
                    payload={
                        "model": self.settings.embedding_model,
                        "input": payload_input,
                        "dimensions": self.settings.embedding_dimensions,
                        "encoding_format": "float",
                    },
                    timeout=self.settings.embedding_timeout_seconds,
                    transport=self._transport,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingUnavailable("embedding_request_failed") from exc
        if self.settings.embedding_provider == "dashscope_multimodal":
            output = payload.get("output") if isinstance(payload, dict) else None
            data = output.get("embeddings") if isinstance(output, dict) else None
        else:
            data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(contents):
            raise EmbeddingUnavailable("embedding_response_mismatch")
        ordered = sorted(data, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list) or len(embedding) != self.settings.embedding_dimensions:
                raise EmbeddingUnavailable("embedding_dimension_mismatch")
            try:
                vectors.append([float(value) for value in embedding])
            except (TypeError, ValueError) as exc:
                raise EmbeddingUnavailable("embedding_value_invalid") from exc
        return vectors

    @property
    def supports_image(self) -> bool:
        return self.settings.embedding_provider == "dashscope_multimodal"


def vector_literal(values: list[float]) -> str:
    """pgvector text literal; floats are repr'd to keep round-trip precision."""
    return "[" + ",".join(repr(float(value)) for value in values) + "]"
