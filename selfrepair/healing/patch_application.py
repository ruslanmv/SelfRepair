from __future__ import annotations

from pathlib import Path


def touch_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
