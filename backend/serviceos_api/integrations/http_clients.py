"""Process-level keep-alive HTTP clients for provider calls.

Reusing connections removes a TLS handshake per LLM/embedding call (~0.2-0.4s).
Callers that inject a transport (tests) always get an ephemeral client.
"""

import threading

import httpx

_CLIENTS: dict[tuple, httpx.Client] = {}
_LOCK = threading.Lock()


def shared_client(base_url: str, timeout: float) -> httpx.Client:
    key = (base_url, timeout)
    with _LOCK:
        client = _CLIENTS.get(key)
        if client is None or client.is_closed:
            client = httpx.Client(timeout=timeout)
            _CLIENTS[key] = client
        return client


def post_json(url: str, *, headers: dict, payload: dict, timeout: float,
              transport: httpx.BaseTransport | None = None) -> httpx.Response:
    if transport is not None:
        with httpx.Client(transport=transport, timeout=timeout) as client:
            return client.post(url, headers=headers, json=payload)
    base = url.rsplit("/", 1)[0]
    return shared_client(base, timeout).post(url, headers=headers, json=payload)
