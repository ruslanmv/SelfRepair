from pathlib import Path

def safe_repo_dir(base: Path, repo_full_name: str) -> Path:
    return base / repo_full_name.replace("/", "__")
