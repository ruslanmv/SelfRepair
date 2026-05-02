import json
from pathlib import Path

import pytest

from selfrepair.sdk import (
    Finding,
    FixerRegistry,
    Patch,
    RepairPlan,
    RepoContext,
    Severity,
)
from selfrepair.sdk.scanner import parse_sarif


class TestFindingFingerprint:
    def test_same_kind_path_and_snippet_have_same_fingerprint(self) -> None:
        a = Finding(kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo bar")
        b = Finding(kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo bar")
        assert a.fingerprint == b.fingerprint

    def test_line_number_does_not_affect_fingerprint(self) -> None:
        a = Finding(
            kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo", line=10
        )
        b = Finding(
            kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo", line=42
        )
        assert a.fingerprint == b.fingerprint

    def test_whitespace_normalization_in_snippet(self) -> None:
        a = Finding(
            kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo  bar"
        )
        b = Finding(
            kind="x", severity=Severity.LOW, file_path="a.py", snippet="foo\tbar"
        )
        assert a.fingerprint == b.fingerprint

    def test_different_path_changes_fingerprint(self) -> None:
        a = Finding(kind="x", severity=Severity.LOW, file_path="a.py", snippet="z")
        b = Finding(kind="x", severity=Severity.LOW, file_path="b.py", snippet="z")
        assert a.fingerprint != b.fingerprint


class _ToyFixer:
    id = "toy"
    handles = ("toy_kind",)
    risk = Severity.LOW

    def matches(self, finding, ctx):
        return True

    def plan(self, finding, ctx):
        return RepairPlan(
            fixer_id=self.id,
            finding=finding,
            summary="toy",
            risk=self.risk,
            files_touched=("a.py",),
        )

    def apply(self, plan, ctx):
        return Patch(
            fixer_id=self.id,
            finding_fingerprint=plan.finding.fingerprint,
            diff="--- a/a.py\n+++ b/a.py\n",
            files_changed=("a.py",),
            summary="toy",
        )


class TestFixerRegistry:
    def test_register_and_match(self, tmp_path: Path) -> None:
        reg = FixerRegistry()
        reg.register(_ToyFixer())
        ctx = RepoContext(
            workspace=tmp_path, full_name="o/r", default_branch="main"
        )
        f = Finding(kind="toy_kind", severity=Severity.LOW, file_path="a.py")
        candidates = list(reg.candidates_for(f, ctx))
        assert len(candidates) == 1
        assert candidates[0].id == "toy"

    def test_double_register_rejected(self) -> None:
        reg = FixerRegistry()
        reg.register(_ToyFixer())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_ToyFixer())

    def test_unknown_kind_yields_no_candidates(self, tmp_path: Path) -> None:
        reg = FixerRegistry()
        reg.register(_ToyFixer())
        ctx = RepoContext(
            workspace=tmp_path, full_name="o/r", default_branch="main"
        )
        f = Finding(kind="other", severity=Severity.LOW, file_path="a.py")
        assert list(reg.candidates_for(f, ctx)) == []


class TestSarifParser:
    def test_parses_minimal_sarif(self, tmp_path: Path) -> None:
        sarif = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "semgrep",
                            "rules": [
                                {
                                    "id": "py.secret",
                                    "defaultLevel": "error",
                                    "properties": {
                                        "tags": ["security", "CWE-798"]
                                    },
                                }
                            ],
                        }
                    },
                    "results": [
                        {
                            "ruleId": "py.secret",
                            "level": "error",
                            "message": {"text": "hardcoded secret"},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/foo.py"},
                                        "region": {"startLine": 12},
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        path = tmp_path / "out.sarif"
        path.write_text(json.dumps(sarif), encoding="utf-8")
        result = parse_sarif(path, scanner_id="semgrep")
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.kind == "semgrep.py.secret"
        assert f.severity == Severity.HIGH
        assert f.cwe == "CWE-798"
        assert f.line == 12
        assert f.file_path == "src/foo.py"

    def test_handles_missing_optional_fields(self, tmp_path: Path) -> None:
        sarif = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "trivy"}},
                    "results": [
                        {"message": {"text": "unknown issue"}, "level": "warning"}
                    ],
                }
            ],
        }
        path = tmp_path / "out.sarif"
        path.write_text(json.dumps(sarif), encoding="utf-8")
        result = parse_sarif(path, scanner_id="trivy")
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.severity == Severity.MEDIUM
        assert f.cwe is None
        assert f.file_path == ""
        assert f.line is None
