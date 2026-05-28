from __future__ import annotations

import logging
from typing import Any

import httpx

from selfrepair.settings import Settings

logger = logging.getLogger(__name__)


class OllaBridgeClient:
    """OpenAI-compatible client for OllaBridge / OllaBridge Cloud.

    Uses the /v1/chat/completions endpoint which is compatible with
    both local OllaBridge and the cloud relay service. The constructor
    accepts either form of base URL -- with or without a trailing
    ``/v1`` -- and normalizes to the form expected by the request
    methods so we never produce ``/v1/v1/chat/completions``.
    """

    def __init__(self, settings: Settings) -> None:
        base = settings.ollabridge_base_url.rstrip("/")
        # The methods below build paths like ``f"{base_url}/v1/..."`` so
        # strip a trailing ``/v1`` if the caller already included it.
        # Both ``https://api.ollabridge.com`` and
        # ``https://api.ollabridge.com/v1`` produce the same effective
        # endpoint.
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        self.base_url = base
        self.api_key = settings.ollabridge_api_key
        self.model = settings.ollabridge_model
        self.timeout = settings.ollabridge_timeout

    def available(self) -> bool:
        """Check if OllaBridge endpoint is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def chat(self, prompt: str, system: str | None = None) -> str:
        """Send a chat completion request and return the assistant message."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }

        resp = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def list_models(self) -> list[str]:
        """List available models from the OllaBridge endpoint."""
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = httpx.get(f"{self.base_url}/v1/models", headers=headers, timeout=10)
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        except Exception as exc:
            logger.warning("Failed to list OllaBridge models: %s", exc)
            return []
