from pathlib import Path

def has_pyproject(repo_dir: Path) -> bool:
    return (repo_dir / "pyproject.toml").exists()
