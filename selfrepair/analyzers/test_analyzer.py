from pathlib import Path

def has_health_test(repo_dir: Path) -> bool:
    return (repo_dir / "tests" / "test_health.py").exists()
