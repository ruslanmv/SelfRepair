from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from selfrepair.git.gitleaks import (
    _redact,
    scan_repo,
)


class TestRedact:
    def test_short_secret_fully_masked(self) -> None:
        assert _redact("abc") == "***"

    def test_long_secret_keeps_ends_only(self) -> None:
        result = _redact("supersecretpassword")
        assert result == "sup***ord"
        assert "supersecretpassword" not in result

    def test_empty_returns_empty(self) -> None:
        assert _redact("") == ""


class TestScanRepo:
    def test_returns_unavailable_when_gitleaks_missing(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "selfrepair.git.gitleaks.is_available", return_value=False
        ):
            result = scan_repo(tmp_path)
        assert result.available is False
        assert result.findings == ()
        assert not result.is_clean

    def test_clean_when_no_findings(self, tmp_path: Path) -> None:
        with patch(
            "selfrepair.git.gitleaks.is_available", return_value=True
        ), patch(
            "selfrepair.git.gitleaks.subprocess.run"
        ) as mock_run:
            mock_run.return_value = None
            # Don't write a report file → empty findings.
            result = scan_repo(tmp_path)
        assert result.available is True
        assert result.findings == ()
        assert result.is_clean

    def test_parses_findings_and_redacts_secret(
        self, tmp_path: Path
    ) -> None:
        report = [
            {
                "RuleID": "aws-key",
                "File": "src/creds.py",
                "StartLine": 12,
                "Secret": "AKIAEXAMPLE12345",
            }
        ]
        report_path = tmp_path / ".gitleaks-report.json"

        def fake_run(cmd, *args, **kwargs):  # noqa: ARG001
            report_path.write_text(
                json.dumps(report), encoding="utf-8"
            )
            return None

        with patch(
            "selfrepair.git.gitleaks.is_available", return_value=True
        ), patch(
            "selfrepair.git.gitleaks.subprocess.run", side_effect=fake_run
        ):
            result = scan_repo(tmp_path)

        assert result.available is True
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.rule_id == "aws-key"
        assert f.file_path == "src/creds.py"
        assert f.line == 12
        assert "***" in f.secret_preview
        assert "AKIAEXAMPLE12345" not in f.secret_preview
