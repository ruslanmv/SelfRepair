from pathlib import Path

def snapshot_path(base: Path, name: str) -> Path:
    return base / f"{name}.json"
