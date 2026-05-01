from __future__ import annotations

from pathlib import Path


def ensure_python311(pyproject: Path) -> bool:
    try:
        return "3.11" in pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
