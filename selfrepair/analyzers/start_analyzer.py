from pathlib import Path

def has_start_target(repo_dir: Path) -> bool:
    path = repo_dir / "Makefile"
    return path.exists() and "start:" in path.read_text(encoding="utf-8")
