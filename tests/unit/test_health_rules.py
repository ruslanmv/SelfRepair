from selfrepair.standards.health_test_rules import ensure_health_test

def test_ensure_health_test(tmp_path):
    ok, changed = ensure_health_test(tmp_path)
    assert ok
    assert (tmp_path / "tests" / "test_health.py").exists()
