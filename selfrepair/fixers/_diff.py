"""Helpers shared across reference fixers.

Keeping diff generation out of each fixer means new fixers add ~50 lines,
not 200, and the diff format stays consistent across the catalog.
"""
from __future__ import annotations

import difflib
from pathlib import Path


def make_unified_diff(
    *,
    file_path: str,
    before: str,
    after: str,
) -> str:
    """Return a unified diff with `a/`/`b/` prefixes (git-compatible).

    Returns the empty string when before == after so callers can short-circuit
    "nothing changed" without inspecting the diff body.
    """
    if before == after:
        return ""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    )
    out = "".join(diff)
    if not out.endswith("\n"):
        out += "\n"
    return out


def read_existing(workspace: Path, relative: str) -> str:
    path = workspace / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""
