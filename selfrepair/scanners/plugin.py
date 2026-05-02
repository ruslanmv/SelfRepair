"""Scanner plugin descriptor (`plugin.yaml`).

Design §5.3: a plugin is a directory with a `plugin.yaml` manifest and
(optionally) a Dockerfile. The runner uses the manifest to build the
docker invocation; output is parsed via `selfrepair.sdk.parse_sarif`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScannerRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: str
    cmd: list[str]
    network: Literal["none", "bridge"] = "none"
    cpu: str = "1"
    memory: str = "2Gi"
    timeout: int = Field(default=300, ge=1, le=3600)


class ScannerPlugin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["scanner"]
    id: str
    version: str
    inputs: list[Literal["workspace_path"]] = Field(
        default_factory=lambda: ["workspace_path"]
    )
    outputs: list[str] = Field(
        default_factory=lambda: ["findings.sarif"]
    )
    runtime: ScannerRuntime

    @field_validator("id")
    @classmethod
    def _id_is_a_safe_slug(cls, v: str) -> str:
        if v != v.lower():
            raise ValueError("scanner id must be lowercase")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "scanner id may only contain a-z 0-9 - _"
            )
        return v


def load_plugin(plugin_dir: Path) -> ScannerPlugin:
    """Load and validate a `plugin.yaml` from `plugin_dir`."""
    manifest = plugin_dir / "plugin.yaml"
    if not manifest.is_file():
        raise FileNotFoundError(f"no plugin.yaml at {plugin_dir}")
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return ScannerPlugin.model_validate(raw)
