"""Configuration of the agent-repair intake, read from the environment on every use.

Fail closed: without a token, a signing secret, an org and an allow-list of repositories, every request is refused.

    SELFREPAIR_AGENT_REPAIR_TOKEN          bearer token LangReplay presents (required)
    SELFREPAIR_AGENT_REPAIR_SECRET         HMAC secret for X-LangReplay-Signature (required)
    SELFREPAIR_AGENT_REPAIR_ORG_ID         the org these requests belong to (required)
    SELFREPAIR_AGENT_REPAIR_REPOS          comma-separated repository URLs that may be repaired (required)
    SELFREPAIR_AGENT_REPAIR_CHECKS         JSON list of argv lists run on base commit + patch, e.g. [["python","-m","pytest","-q"]]
    SELFREPAIR_AGENT_REPAIR_CHECK_TIMEOUT  seconds per check command (default 600)
    SELFREPAIR_AGENT_REPAIR_MAX_RETRIES    implementations after the first one (default 2)
    SELFREPAIR_AGENT_REPAIR_ALLOW_DEMO_CODER  "true" only for trials: accept GitPilot's demo coder
    SELFREPAIR_AGENT_REPAIR_GITHUB_TOKEN   token that may push the candidate branch and open the draft PR
    SELFREPAIR_AGENT_REPAIR_INLINE         "true" in a single-process setup without the worker queue
    SELFREPAIR_AGENT_REPAIR_CODER_PROVIDER / _CODER_MODEL   passed to GitPilot (default ollabridge / code-coder)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_SKEW_SECONDS = 300


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_repo_url(url: str) -> str:
    """`https://GitHub.com/Acme/Agent.git/` -> `https://github.com/acme/agent` (a local path is kept as given)."""
    raw = (url or "").strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    parts = urlsplit(raw)
    if parts.scheme in ("http", "https"):
        return f"{parts.scheme}://{(parts.hostname or '').lower()}{parts.path.lower()}"
    return raw


@dataclass(frozen=True)
class AgentRepairSettings:
    token: str
    secret: str
    org_id: uuid.UUID | None
    repos: frozenset[str]
    checks: list[list[str]] = field(default_factory=list)
    check_timeout_s: int = 600
    max_retries: int = 2
    allow_demo_coder: bool = False
    github_token: str | None = None
    inline: bool = False
    coder_provider: str = "ollabridge"
    coder_model: str = "code-coder"

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.secret and self.org_id and self.repos)

    def repo_allowed(self, url: str) -> bool:
        return normalize_repo_url(url) in self.repos


def load() -> AgentRepairSettings:
    env = os.environ
    org = env.get("SELFREPAIR_AGENT_REPAIR_ORG_ID", "").strip()
    try:
        org_id = uuid.UUID(org) if org else None
    except ValueError:
        org_id = None
    try:
        checks = json.loads(env.get("SELFREPAIR_AGENT_REPAIR_CHECKS", "[]") or "[]")
        checks = [[str(a) for a in c] for c in checks if isinstance(c, list) and c]
    except ValueError:
        checks = []
    return AgentRepairSettings(
        token=env.get("SELFREPAIR_AGENT_REPAIR_TOKEN", "").strip(),
        secret=env.get("SELFREPAIR_AGENT_REPAIR_SECRET", "").strip(),
        org_id=org_id,
        repos=frozenset(normalize_repo_url(u) for u in env.get("SELFREPAIR_AGENT_REPAIR_REPOS", "").split(",") if u.strip()),
        checks=checks,
        check_timeout_s=int(env.get("SELFREPAIR_AGENT_REPAIR_CHECK_TIMEOUT", "600") or 600),
        max_retries=int(env.get("SELFREPAIR_AGENT_REPAIR_MAX_RETRIES", "2") or 2),
        allow_demo_coder=_truthy(env.get("SELFREPAIR_AGENT_REPAIR_ALLOW_DEMO_CODER")),
        github_token=(env.get("SELFREPAIR_AGENT_REPAIR_GITHUB_TOKEN") or "").strip() or None,
        inline=_truthy(env.get("SELFREPAIR_AGENT_REPAIR_INLINE")),
        coder_provider=env.get("SELFREPAIR_AGENT_REPAIR_CODER_PROVIDER", "ollabridge") or "ollabridge",
        coder_model=env.get("SELFREPAIR_AGENT_REPAIR_CODER_MODEL", "code-coder") or "code-coder",
    )
