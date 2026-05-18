"""End-to-end repair demo: break a tiny Python file, let the LLM fix it.

Demonstrates that the SelfRepair LLM repair path actually works against
the OllaBridge Cloud relay this device is paired with. The flow mirrors
the worker's `repair` stage in miniature:

1. Drop a broken `hello.py` into a temp workdir. The bug is a real one
   that the interpreter rejects (syntax + a missing import) so we can
   verify the fix by re-running the file at the end.
2. Read the broken source, send it to the LLM with a repair-focused
   system prompt, and ask for the corrected file back.
3. Strip any code-fence wrapping the model adds, write the patched file
   back, and run it. The verification step is `python hello.py`
   succeeding with the expected output.

Run::

    OLLABRIDGE_BASE_URL=https://ruslanmv-ollabridge.hf.space \\
    OLLABRIDGE_API_KEY=<device-token> \\
    OLLABRIDGE_MODEL=qwen2.5:1.5b \\
    .venv/bin/python -m examples.repair_demo
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from selfrepair.llm.ollabridge_client import OllaBridgeClient


# A two-bug Python file: a missing import and a stray colon. Both make
# the file fail at parse / runtime, and both are the kind of thing a
# repair-focused model fixes deterministically.
BROKEN_SOURCE = '''\
"""A tiny health probe. Intentionally broken for the repair demo."""

def healthcheck():
    # Bug 1: `json` was never imported.
    return json.dumps({"status": "ok"})


if __name__ == "__main__":
    # Bug 2: stray colon turns this into a SyntaxError.
    print(healthcheck()):
'''

EXPECTED_OUTPUT_SUBSTRING = '"status": "ok"'


SYSTEM_PROMPT = (
    "You are SelfRepair-bot, an automated Python repair tool. "
    "You receive a single Python source file that is failing. "
    "Reply with the corrected source ONLY. "
    "Do not include any prose, explanation, or markdown — just raw "
    "Python code that, when written verbatim to a `.py` file, parses "
    "and runs successfully."
)

USER_PROMPT_TEMPLATE = (
    "Fix the following Python file so that it parses and prints a JSON "
    "health status when executed. Return the corrected source only.\n\n"
    "```python\n{source}\n```"
)


@dataclass
class _Settings:
    ollabridge_base_url: str
    ollabridge_api_key: str
    ollabridge_model: str
    ollabridge_timeout: float = 120.0


def _build_client() -> OllaBridgeClient:
    base = os.getenv(
        "OLLABRIDGE_BASE_URL", "https://ruslanmv-ollabridge.hf.space"
    )
    key = os.getenv("OLLABRIDGE_API_KEY", "")
    model = os.getenv("OLLABRIDGE_MODEL", "qwen2.5:1.5b")
    if not key:
        sys.exit(
            "OLLABRIDGE_API_KEY is required (device token from "
            "/device/pair-simple)."
        )
    return OllaBridgeClient(
        _Settings(
            ollabridge_base_url=base + "/ollama",
            ollabridge_api_key=key,
            ollabridge_model=model,
        )
    )


_CODE_FENCE = re.compile(r"^```[a-zA-Z0-9_\-]*\n|\n```\s*$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """Models sometimes wrap the answer in ```python ... ```. Strip it."""
    text = text.strip()
    if text.startswith("```"):
        text = _CODE_FENCE.sub("", text).strip()
    return text


def _confirm_python_parses(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, proc.stderr.strip()


def _run_python(path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    client = _build_client()
    print(f"OllaBridge:  {client.base_url}")
    print(f"Model:       {client.model}")
    print()

    with tempfile.TemporaryDirectory(prefix="selfrepair-demo-") as tmp:
        workdir = Path(tmp)
        target = workdir / "hello.py"
        target.write_text(BROKEN_SOURCE)

        # --- BEFORE -------------------------------------------------------
        ok_before, parse_err = _confirm_python_parses(target)
        print(f"[before] {target.name} parses?  {ok_before}")
        if parse_err:
            first_err = parse_err.splitlines()[-1]
            print(f"[before] parser says:        {first_err}")
        print()

        if ok_before:
            print("Source already parses; the demo expects a broken file.")
            return 1

        # --- LLM repair --------------------------------------------------
        print(f"[repair] sending {len(target.read_text())} bytes to LLM…")
        fixed = client.chat(
            USER_PROMPT_TEMPLATE.format(source=target.read_text()),
            system=SYSTEM_PROMPT,
        )
        fixed = _strip_code_fence(fixed)
        if not fixed:
            print("[repair] LLM returned empty response; aborting.")
            return 2
        target.write_text(fixed)
        print(f"[repair] applied {len(fixed)} bytes to {target.name}")
        print()

        # --- AFTER --------------------------------------------------------
        ok_after, parse_err = _confirm_python_parses(target)
        print(f"[after]  {target.name} parses?   {ok_after}")
        if not ok_after:
            print(f"[after]  parser says:         {parse_err.splitlines()[-1]}")
            print()
            print("--- patched source ---")
            print(target.read_text())
            return 3

        rc, stdout, stderr = _run_python(target)
        print(f"[after]  exit code:           {rc}")
        if stdout:
            print(f"[after]  stdout:              {stdout.strip()}")
        if stderr:
            print(f"[after]  stderr:              {stderr.strip()}")
        print()

        if rc == 0 and EXPECTED_OUTPUT_SUBSTRING in stdout:
            print("REPAIR VERIFIED ✓  (parses, runs, prints expected output)")
            return 0
        print("REPAIR FAILED — file parses but doesn't behave as expected.")
        print("--- patched source ---")
        print(target.read_text())
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
