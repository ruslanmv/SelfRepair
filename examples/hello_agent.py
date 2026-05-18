"""Hello-world SelfRepair agent backed by OllaBridge cloud.

Walks the smallest possible loop end-to-end:

1. Build an `OllaBridgeClient` that points at the OllaBridge cloud relay
   the operator paired this device with.
2. Hand it a system prompt that gives the agent a small repair-tool
   personality and a single user message.
3. Print the assistant's reply, plus a couple of follow-up turns so
   the read-out shows it can carry conversation state.

Run it with::

    OLLABRIDGE_BASE_URL=https://ruslanmv-ollabridge.hf.space \
    OLLABRIDGE_API_KEY=<device-token-from-/device/pair-simple> \
    OLLABRIDGE_MODEL=qwen2.5:1.5b \
    .venv/bin/python -m examples.hello_agent

Defaults match the SelfRepair settings shape so a `.env` populated
the same way as the rest of the project also works.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from selfrepair.llm.ollabridge_client import OllaBridgeClient


@dataclass
class _Settings:
    """Minimal duck-typed Settings stand-in for the OllaBridgeClient.

    The full `selfrepair.settings.Settings` class pulls in repo, GitHub
    App, sandbox, and CI configuration that this hello-world doesn't
    need. The client only reads four attributes; we provide just those
    so this script can run from a fresh clone without a populated .env.
    """

    ollabridge_base_url: str
    ollabridge_api_key: str
    ollabridge_model: str
    ollabridge_timeout: float = 60.0


def _build_client() -> OllaBridgeClient:
    base_url = os.getenv(
        "OLLABRIDGE_BASE_URL", "https://ruslanmv-ollabridge.hf.space"
    )
    # Token is what /device/pair-simple returned. Treated as a Bearer
    # token by the OllaBridge OpenAI-compatible /ollama/v1 surface.
    api_key = os.getenv("OLLABRIDGE_API_KEY", "")
    if not api_key:
        sys.exit(
            "OLLABRIDGE_API_KEY is required. Pair this device first:\n"
            "  curl -X POST https://ruslanmv-ollabridge.hf.space/device/pair-simple \\\n"
            "       -H 'Content-Type: application/json' \\\n"
            "       -d '{\"code\":\"<your-pairing-code>\"}'\n"
            "and export the device_token it returns as OLLABRIDGE_API_KEY."
        )
    # `qwen2.5:1.5b` is the model the OllaBridge cloud relay returns
    # tokens for in the smoke-test path; any other id from
    # `/ollama/v1/models` works too.
    model = os.getenv("OLLABRIDGE_MODEL", "qwen2.5:1.5b")

    settings = _Settings(
        ollabridge_base_url=base_url + "/ollama",
        ollabridge_api_key=api_key,
        ollabridge_model=model,
    )
    return OllaBridgeClient(settings)


SYSTEM_PROMPT = (
    "You are SelfRepair-bot, a careful repository-health assistant. "
    "Reply concisely. When the user greets you, respond with a one-line "
    "hello, name the model you are running on, and offer two example "
    "things you can do."
)


def main() -> int:
    client = _build_client()
    print(f"Talking to {client.base_url} with model={client.model}")
    print()

    turns = [
        "Hello, agent! Confirm you are alive and connected via OllaBridge.",
        "What is one thing SelfRepair would auto-fix in a Python repo?",
        "Sign off with a single short emoji-free sentence.",
    ]
    for i, prompt in enumerate(turns, start=1):
        print(f"→ user [{i}]: {prompt}")
        reply = client.chat(prompt, system=SYSTEM_PROMPT)
        print(f"← bot  [{i}]: {reply.strip()}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
