from __future__ import annotations

from pathlib import Path

from selfrepair.fixers import (
    HealthTestFixer,
    MakefileFixer,
    PyProjectFixer,
    default_registry,
)
from selfrepair.sdk.models import Finding, RepoContext, Severity


def _ctx(workspace: Path) -> RepoContext:
    return RepoContext(
        workspace=workspace,
        full_name="agent-matrix/demo",
        default_branch="main",
    )


class TestMakefileFixer:
    def test_creates_makefile_when_missing(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        fixer = MakefileFixer()
        finding = Finding(
            kind="makefile_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert patch.diff
        assert "Makefile" in patch.files_changed
        assert "install:" in patch.diff
        assert "test:" in patch.diff
        assert "start:" in patch.diff

    def test_appends_missing_targets_only(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").write_text(
            "install:\n\tpip install -e .\n", encoding="utf-8"
        )
        ctx = _ctx(tmp_path)
        fixer = MakefileFixer()
        finding = Finding(
            kind="makefile_targets_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert "test:" in patch.diff
        assert "start:" in patch.diff
        # `install:` was already present, so we should not re-add it.
        added_lines = [
            line for line in patch.diff.splitlines() if line.startswith("+")
        ]
        re_added_install = [
            line for line in added_lines
            if line.lstrip("+").startswith("install:")
        ]
        assert not re_added_install

    def test_no_diff_when_all_targets_present(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").write_text(
            "install:\n\ttrue\n\ntest:\n\ttrue\n\nstart:\n\ttrue\n",
            encoding="utf-8",
        )
        ctx = _ctx(tmp_path)
        fixer = MakefileFixer()
        finding = Finding(
            kind="makefile_targets_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert patch.diff == ""
        assert patch.files_changed == ()

    def test_matches_only_known_kinds(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        fixer = MakefileFixer()
        assert fixer.matches(
            Finding(
                kind="makefile_missing",
                severity=Severity.LOW,
                file_path="Makefile",
            ),
            ctx,
        )
        assert not fixer.matches(
            Finding(kind="other", severity=Severity.LOW, file_path="x"),
            ctx,
        )


class TestPyProjectFixer:
    def test_creates_pyproject_when_missing(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        fixer = PyProjectFixer()
        finding = Finding(
            kind="pyproject_missing",
            severity=Severity.LOW,
            file_path="pyproject.toml",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert "requires-python" in patch.diff
        assert ">=3.11" in patch.diff
        assert "[tool.uv]" in patch.diff
        assert 'name = "demo"' in patch.diff

    def test_updates_python_version_in_existing(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.8"\n',
            encoding="utf-8",
        )
        ctx = _ctx(tmp_path)
        fixer = PyProjectFixer()
        finding = Finding(
            kind="pyproject_python_version",
            severity=Severity.LOW,
            file_path="pyproject.toml",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert ">=3.11,<3.13" in patch.diff
        assert "3.8" in patch.diff  # in the `-` line

    def test_adds_uv_section_when_missing(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.11"\n',
            encoding="utf-8",
        )
        ctx = _ctx(tmp_path)
        fixer = PyProjectFixer()
        finding = Finding(
            kind="pyproject_uv_missing",
            severity=Severity.LOW,
            file_path="pyproject.toml",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert "[tool.uv]" in patch.diff


class TestHealthTestFixer:
    def test_creates_health_test_when_missing(self, tmp_path: Path) -> None:
        ctx = _ctx(tmp_path)
        fixer = HealthTestFixer()
        finding = Finding(
            kind="health_test_missing",
            severity=Severity.LOW,
            file_path="tests/test_health.py",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert "test_package_imports" in patch.diff
        assert "tests/test_health.py" in patch.files_changed

    def test_no_diff_when_already_present(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_health.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8"
        )
        ctx = _ctx(tmp_path)
        fixer = HealthTestFixer()
        finding = Finding(
            kind="health_test_missing",
            severity=Severity.LOW,
            file_path="tests/test_health.py",
        )
        patch = fixer.apply(fixer.plan(finding, ctx), ctx)
        assert patch.diff == ""


class TestDefaultRegistry:
    def test_registers_three_fixers(self) -> None:
        assert len(default_registry()) == 3

    def test_finds_correct_fixer_for_kind(self, tmp_path: Path) -> None:
        registry = default_registry()
        ctx = _ctx(tmp_path)
        finding = Finding(
            kind="makefile_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        candidates = list(registry.candidates_for(finding, ctx))
        assert len(candidates) == 1
        assert candidates[0].id == "py.makefile"
