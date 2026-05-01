from __future__ import annotations

from pathlib import Path


def ensure_uv(pyproject: Path) -> bool:
    try:
        return "[tool.uv]" in pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
