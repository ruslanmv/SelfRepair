"""Discover scanner plugins from `plugins/scanners/` and SELFREPAIR_SCANNER_PATH.

Each immediate child directory of a root that contains `plugin.yaml` is a
plugin. First root wins on id conflicts so user-provided paths can override
the bundled scanners by id.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from selfrepair.scanners.plugin import ScannerPlugin, load_plugin

logger = logging.getLogger(__name__)


def discover_scanners(root: Path | None = None) -> list[ScannerPlugin]:
    roots: list[Path] = []
    if root is not None:
        roots.append(root)
    env = os.environ.get("SELFREPAIR_SCANNER_PATH", "")
    for entry in env.split(":"):
        if entry:
            roots.append(Path(entry))
    if not roots:
        default = (
            Path(__file__).resolve().parents[2]
            / "plugins"
            / "scanners"
        )
        if default.is_dir():
            roots.append(default)

    scanners: list[ScannerPlugin] = []
    seen: set[str] = set()
    for r in roots:
        if not r.is_dir():
            continue
        for child in sorted(r.iterdir()):
            if not child.is_dir():
                continue
            try:
                plugin = load_plugin(child)
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.warning(
                    "skipping invalid plugin at %s: %s", child, exc
                )
                continue
            if plugin.id in seen:
                logger.info(
                    "scanner %s already loaded; skipping %s",
                    plugin.id, child,
                )
                continue
            seen.add(plugin.id)
            scanners.append(plugin)
    return scanners
