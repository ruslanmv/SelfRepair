"""Resolve reviewer configuration from defaults, org rows, and the repo file.

Order, lowest precedence first:

1. Code defaults (`enabled: false`, engine `deterministic`).
2. Organization settings stored by the API.
3. The repository's `.selfrepair.yml` `reviewer` section.
4. The per-repository API override.

An existing repository with no reviewer section stays disabled.
"""
from __future__ import annotations

from typing import Any

import yaml

from selfrepair.config.repo_config import RepoConfig, ReviewerConfig


def reviewer_from_yaml(config_yaml: str | None) -> ReviewerConfig:
    """Return the reviewer section of a stored `.selfrepair.yml`, or defaults."""
    if not config_yaml or not config_yaml.strip():
        return ReviewerConfig()
    raw = yaml.safe_load(config_yaml) or {}
    if not isinstance(raw, dict):
        return ReviewerConfig()
    return RepoConfig.model_validate(raw).reviewer


def reviewer_overrides_from_yaml(config_yaml: str | None) -> dict[str, Any]:
    """Only the reviewer fields the repository file actually sets.

    The section is validated in full first (so `auto_merge: true` and unknown
    keys are still rejected), but defaults are not returned: a field the file
    omits must inherit the organization setting, not reset it to the code
    default.
    """
    return reviewer_from_yaml(config_yaml).model_dump(exclude_unset=True)


def explicit_settings(config: ReviewerConfig) -> dict[str, Any]:
    """What a settings API call should store: only the fields it set."""
    return config.model_dump(exclude_unset=True)


def resolve_reviewer_config(
    *,
    config_yaml: str | None,
    org_settings: dict[str, Any] | None,
    repo_settings: dict[str, Any] | None,
) -> ReviewerConfig:
    """Merge the four layers into one config."""
    merged = ReviewerConfig().model_dump()
    merged = _deep_merge(merged, org_settings or {})
    merged = _deep_merge(merged, reviewer_overrides_from_yaml(config_yaml))
    merged = _deep_merge(merged, repo_settings or {})
    return ReviewerConfig.model_validate(merged)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        current = out.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            out[key] = _deep_merge(current, value)
        else:
            out[key] = value
    return out
