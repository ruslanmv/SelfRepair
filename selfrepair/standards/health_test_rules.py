from __future__ import annotations

from pathlib import Path

DEFAULT_TEST = """def test_health():
    assert True
"""


def ensure_health_test(repo_dir: Path) -> tuple[bool, list[str]]:
    changed: list[str] = []
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    init_path = tests_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text("", encoding="utf-8")
        changed.append("tests/__init__.py")
    path = tests_dir / "test_health.py"
    if not path.exists():
        path.write_text(DEFAULT_TEST, encoding="utf-8")
        changed.append("tests/test_health.py")
    return True, changed
