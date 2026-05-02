from __future__ import annotations

from selfrepair.standards.makefile_rules import ensure_makefile


def test_ensure_makefile(tmp_path):
    ok, changed = ensure_makefile(tmp_path)
    assert ok
    assert (tmp_path / "Makefile").exists()
    assert "Makefile" in changed
