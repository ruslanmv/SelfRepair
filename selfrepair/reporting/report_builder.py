"""Audit-ready report builder for the repository-maintenance product.

Produces report.json, report.md and status.html from a repair-plan, the
GitPilot repair-response and the MatrixLab validation result. SelfRepair's job
ends here: it DIAGNOSED, PLANNED, DELEGATED and now REPORTS.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


def build_report_data(
    *,
    plan: Any,
    repair_response: Any = None,
    validation_result: Any = None,
    validation_skipped: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the structured report payload (the source for all formats)."""
    plan_d = _as_dict(plan)
    repair_d = _as_dict(repair_response)
    validation_d = _as_dict(validation_result)

    return {
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "client_id": plan_d.get("client_id"),
        "workspace_id": plan_d.get("workspace_id"),
        "task_id": plan_d.get("task_id"),
        "repo_url": plan_d.get("repo_url"),
        "branch": plan_d.get("branch"),
        "mode": plan_d.get("mode", "dry_run"),
        "health_score": plan_d.get("health_score"),
        "issues": plan_d.get("issues", []),
        "allowed_paths": plan_d.get("allowed_paths", []),
        "forbidden_paths": plan_d.get("forbidden_paths", []),
        "coder": plan_d.get("coder", {}),
        "sandbox": plan_d.get("sandbox", {}),
        "plan": plan_d,
        "repair": repair_d,
        "validation": {
            "skipped": validation_skipped,
            "result": validation_d,
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Repository Repair Report — {data.get('repo_url', 'unknown')}")
    lines.append("")
    lines.append(f"- **Generated:** {data.get('generated_at')}")
    lines.append(f"- **Client:** {data.get('client_id')}")
    lines.append(f"- **Workspace:** {data.get('workspace_id')}")
    lines.append(f"- **Task:** {data.get('task_id')}")
    lines.append(f"- **Branch:** {data.get('branch')}")
    lines.append(f"- **Mode:** {data.get('mode')}")
    lines.append(f"- **Health score:** {data.get('health_score')} / 100")
    lines.append("")

    issues = data.get("issues", []) or []
    lines.append(f"## Issues ({len(issues)})")
    lines.append("")
    if issues:
        lines.append("| ID | Severity | Description | Recommended action |")
        lines.append("| --- | --- | --- | --- |")
        for issue in issues:
            lines.append(
                f"| {issue.get('id', '')} | {issue.get('severity', '')} | "
                f"{issue.get('description', '')} | {issue.get('recommended_action', '')} |"
            )
    else:
        lines.append("_No issues detected._")
    lines.append("")

    repair = data.get("repair", {}) or {}
    lines.append("## Repair (GitPilot)")
    lines.append("")
    if repair:
        lines.append(f"- **Status:** {repair.get('status', 'n/a')}")
        lines.append(f"- **Risk level:** {repair.get('risk_level', 'n/a')}")
        lines.append(f"- **Stubbed:** {repair.get('stubbed', False)}")
        changed = repair.get("changed_files", []) or []
        lines.append(f"- **Changed files ({len(changed)}):** {', '.join(changed) or 'none'}")
    else:
        lines.append("_No repair response._")
    lines.append("")

    validation = data.get("validation", {}) or {}
    lines.append("## Validation (MatrixLab)")
    lines.append("")
    if validation.get("skipped"):
        lines.append("_Validation skipped._")
    else:
        result = validation.get("result", {}) or {}
        lines.append(f"- **Status:** {result.get('status', 'n/a')}")
        lines.append(f"- **Exit code:** {result.get('exit_code', 'n/a')}")
        lines.append(f"- **Duration:** {result.get('duration_ms', 0)} ms")
    lines.append("")

    lines.append("## Guardrails")
    lines.append("")
    lines.append(f"- **Allowed paths:** {', '.join(data.get('allowed_paths', []) or []) or 'none'}")
    lines.append(f"- **Forbidden paths:** {', '.join(data.get('forbidden_paths', []) or [])}")
    lines.append("")
    return "\n".join(lines)


def render_html(data: dict[str, Any]) -> str:
    issues = data.get("issues", []) or []
    rows = "".join(
        f"<tr><td>{i.get('id','')}</td><td>{i.get('severity','')}</td>"
        f"<td>{i.get('description','')}</td><td>{i.get('recommended_action','')}</td></tr>"
        for i in issues
    )
    repair = data.get("repair", {}) or {}
    validation = data.get("validation", {}) or {}
    val_status = "skipped" if validation.get("skipped") else (
        (validation.get("result", {}) or {}).get("status", "n/a")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Repair Report — {data.get('repo_url','')}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
.score {{ font-size: 1.4rem; font-weight: 700; }}
</style>
</head>
<body>
<h1>Repository Repair Report</h1>
<p><strong>Repo:</strong> {data.get('repo_url','')} &middot;
   <strong>Branch:</strong> {data.get('branch','')} &middot;
   <strong>Mode:</strong> {data.get('mode','')}</p>
<p class="score">Health score: {data.get('health_score')} / 100</p>
<p><strong>Client:</strong> {data.get('client_id')} &middot;
   <strong>Task:</strong> {data.get('task_id')}</p>
<h2>Issues ({len(issues)})</h2>
<table>
<thead><tr><th>ID</th><th>Severity</th><th>Description</th><th>Recommended action</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4">No issues detected.</td></tr>'}</tbody>
</table>
<h2>Repair (GitPilot)</h2>
<p>Status: {repair.get('status','n/a')} &middot; Risk: {repair.get('risk_level','n/a')} &middot;
   Stubbed: {repair.get('stubbed', False)}</p>
<h2>Validation (MatrixLab)</h2>
<p>Status: {val_status}</p>
</body>
</html>
"""


def build_reports(
    *,
    plan: Any,
    repair_response: Any = None,
    validation_result: Any = None,
    validation_skipped: bool = False,
    output_dir: str | Path,
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write report.json, report.md and status.html into *output_dir*.

    Returns a mapping of {"json"|"md"|"html": Path}.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = build_report_data(
        plan=plan,
        repair_response=repair_response,
        validation_result=validation_result,
        validation_skipped=validation_skipped,
        generated_at=generated_at,
    )

    json_path = out / "report.json"
    md_path = out / "report.md"
    html_path = out / "status.html"

    json_path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")

    return {"json": json_path, "md": md_path, "html": html_path}
