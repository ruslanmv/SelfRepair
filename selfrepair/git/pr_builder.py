"""PR body rendering using the Jinja2 template at templates/pr_body.md.j2."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2

from selfrepair.sdk.models import Finding, RepairPlan

_DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "templates" / "pr_body.md.j2"
)


@dataclass(frozen=True)
class PRBodyContext:
    finding: Finding
    plan: RepairPlan
    files_changed: tuple[str, ...]
    summary: str
    rationale: str
    commit_sha: str
    provenance: dict[str, Any]
    selfrepair_url: str = "https://github.com/ruslanmv/SelfRepair"


def render_pr_body(ctx: PRBodyContext, template_path: Path | None = None) -> str:
    template_path = template_path or _DEFAULT_TEMPLATE_PATH
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_path.parent),
        autoescape=False,  # markdown: do not html-escape
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)
    return template.render(
        finding=ctx.finding,
        plan=ctx.plan,
        files_changed=list(ctx.files_changed),
        summary=ctx.summary,
        rationale=ctx.rationale,
        commit_sha=ctx.commit_sha,
        provenance=ctx.provenance,
        selfrepair_url=ctx.selfrepair_url,
    )
