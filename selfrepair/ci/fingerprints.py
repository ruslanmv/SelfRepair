"""Stable fingerprints for deduplicating CI failures across runs.

Naive fingerprints either dedupe too much (everything looks the same) or
too little (every run is unique). The same trick that makes Sentry dedupe
well: hash a normalized error signature, not the raw line.
"""
from __future__ import annotations

import hashlib
import re

# Strip absolute /home/runner/work/... paths; replace with <runner>/...
_RUNNER_PATH = re.compile(r"/home/runner/work/[^\s]+/")
# Strip line numbers in `path/to/file.py:142` -> `path/to/file.py:N`
_LINE_NUM = re.compile(r"(\.[a-zA-Z]+):\d+")
# Strip duration suffixes
_DURATION = re.compile(r"\d+(\.\d+)?(?:ms|s|m|h)\b")
# Strip hex hashes (8+ chars; commit shas, content hashes)
_HEX_HASH = re.compile(r"\b[a-f0-9]{8,}\b")
# Strip GUIDs
_GUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# Strip ISO timestamps
_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")
# Strip ANSI colour codes
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Strip stack-frame addresses (0x...)
_HEX_ADDR = re.compile(r"0x[0-9a-fA-F]{4,}")
# Collapse runs of whitespace
_WHITESPACE = re.compile(r"\s+")


def normalize_signature(line: str) -> str:
    """Reduce a single error line to its semantic shape.

    The same logical error from two runs yields the same string.
    """
    s = line
    s = _ANSI.sub("", s)
    s = _RUNNER_PATH.sub("<runner>/", s)
    s = _ISO_TS.sub("<ts>", s)
    s = _GUID.sub("<guid>", s)
    s = _DURATION.sub("<dur>", s)
    s = _HEX_ADDR.sub("0x<addr>", s)
    s = _LINE_NUM.sub(r"\1:N", s)
    s = _HEX_HASH.sub("<hex>", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


def compute_fingerprint(
    *,
    repo_id: str,
    workflow_path: str,
    failed_job_name: str,
    failed_step_name: str,
    failure_class: str,
    error_signature: str,
) -> str:
    """SHA-256-based fingerprint, truncated to 32 hex chars (16 bytes).

    Uses workflow_path (not workflow_name) so workflow renames don't reset
    history. Falls back to step name if `error_signature` is empty.
    """
    sig = error_signature or f"step:{failed_step_name}"
    parts = [
        repo_id,
        workflow_path,
        failed_job_name,
        failed_step_name,
        failure_class,
        sig,
    ]
    material = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]
