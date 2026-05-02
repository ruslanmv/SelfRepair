from __future__ import annotations

from selfrepair.standards.pyproject_rules import ensure_pyproject


def test_ensure_pyproject(tmp_path):
    ok, changed = ensure_pyproject(tmp_path, "demo")
    assert ok
    text = (tmp_path / "pyproject.toml").read_text()
    assert "3.11" in text
    assert "[tool.uv]" in text
