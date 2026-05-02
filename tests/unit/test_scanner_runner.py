from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from selfrepair.scanners import (
    DockerNotInstalled,
    discover_scanners,
    load_plugin,
    run_scanner,
)


def _plugin_dir(parent: Path, *, plugin_id: str = "demo") -> Path:
    plugin_dir = parent / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        f"""
kind: scanner
id: {plugin_id}
version: "1.0.0"
inputs:
  - workspace_path
outputs:
  - findings.sarif
runtime:
  image: example/{plugin_id}:1.0
  cmd:
    - "scan"
    - "/in"
  network: none
  cpu: "1"
  memory: "2Gi"
  timeout: 60
""",
        encoding="utf-8",
    )
    return plugin_dir


class TestLoadPlugin:
    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        plugin = load_plugin(_plugin_dir(tmp_path, plugin_id="demo"))
        assert plugin.id == "demo"
        assert plugin.kind == "scanner"
        assert plugin.runtime.network == "none"
        assert plugin.runtime.image == "example/demo:1.0"
        assert plugin.runtime.timeout == 60

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_plugin(tmp_path)

    def test_uppercase_id_rejected(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "p"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.yaml").write_text(
            """
kind: scanner
id: BadID
version: "1.0"
runtime:
  image: x
  cmd: ["scan"]
""",
            encoding="utf-8",
        )
        # Pydantic v2 raises ValidationError on the lowercase-slug rule;
        # we assert the specific exception so a different error doesn't
        # masquerade as a passing test (B017).
        with pytest.raises(ValidationError):
            load_plugin(plugin_dir)


class TestDiscoverScanners:
    def test_discovers_multiple(self, tmp_path: Path) -> None:
        _plugin_dir(tmp_path, plugin_id="alpha")
        _plugin_dir(tmp_path, plugin_id="beta")
        scanners = discover_scanners(tmp_path)
        assert {s.id for s in scanners} == {"alpha", "beta"}

    def test_skips_directories_without_manifest(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "noplugin").mkdir()
        _plugin_dir(tmp_path, plugin_id="real")
        scanners = discover_scanners(tmp_path)
        assert {s.id for s in scanners} == {"real"}

    def test_first_root_wins_on_id_conflict(self, tmp_path: Path) -> None:
        primary = tmp_path / "primary"
        primary.mkdir()
        secondary = tmp_path / "secondary"
        secondary.mkdir()
        _plugin_dir(primary, plugin_id="dup")
        _plugin_dir(secondary, plugin_id="dup")
        with patch.dict(
            "os.environ", {"SELFREPAIR_SCANNER_PATH": str(secondary)}
        ):
            scanners = discover_scanners(primary)
        assert len(scanners) == 1


class TestRunScanner:
    def test_raises_when_docker_missing(self, tmp_path: Path) -> None:
        plugin = load_plugin(_plugin_dir(tmp_path, plugin_id="x"))
        workspace = tmp_path / "ws"
        workspace.mkdir()
        with patch(
            "selfrepair.scanners.runner.docker_available",
            return_value=False,
        ):
            with pytest.raises(DockerNotInstalled):
                run_scanner(plugin, workspace=workspace)

    def test_parses_sarif_when_present(self, tmp_path: Path) -> None:
        plugin = load_plugin(_plugin_dir(tmp_path, plugin_id="x"))
        workspace = tmp_path / "ws"
        workspace.mkdir()
        out_root = tmp_path / "out"

        sarif = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "x"}},
                    "results": [
                        {
                            "ruleId": "demo-rule",
                            "level": "error",
                            "message": {"text": "demo"},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "a.py"},
                                        "region": {"startLine": 1},
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        def fake_run(cmd, *args, **kwargs):  # noqa: ARG001
            out_root.mkdir(parents=True, exist_ok=True)
            (out_root / "findings.sarif").write_text(
                json.dumps(sarif), encoding="utf-8"
            )
            return SimpleNamespace(
                returncode=0, stdout=b"", stderr=b""
            )

        with patch(
            "selfrepair.scanners.runner.docker_available",
            return_value=True,
        ), patch(
            "selfrepair.scanners.runner.subprocess.run",
            side_effect=fake_run,
        ):
            result = run_scanner(
                plugin, workspace=workspace, output_root=out_root
            )

        assert result.plugin_id == "x"
        assert len(result.sarif_result.findings) == 1
        assert result.sarif_result.findings[0].rule_id == "demo-rule"

    def test_returns_empty_findings_when_sarif_absent(
        self, tmp_path: Path
    ) -> None:
        plugin = load_plugin(_plugin_dir(tmp_path, plugin_id="x"))
        workspace = tmp_path / "ws"
        workspace.mkdir()
        out_root = tmp_path / "out"

        with patch(
            "selfrepair.scanners.runner.docker_available",
            return_value=True,
        ), patch(
            "selfrepair.scanners.runner.subprocess.run",
            return_value=SimpleNamespace(
                returncode=1, stdout=b"", stderr=b"err"
            ),
        ):
            result = run_scanner(
                plugin, workspace=workspace, output_root=out_root
            )

        assert result.sarif_result.findings == ()
        assert result.returncode == 1
