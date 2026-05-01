from pathlib import Path

def has_makefile(repo_dir: Path) -> bool:
    return (repo_dir / "Makefile").exists()
