"""HuggingFace Space healer.

Uses OllaBridge LLM to analyze broken Spaces and generate fixes:
1. Analyzes Space diagnosis (from space_analyzer)
2. Builds a repair prompt with context
3. Calls OllaBridge for intelligent fix suggestions
4. Applies fixes (new app.py, requirements.txt, README updates)
5. Manages hardware (ZeroGPU allocation)

Falls back to template-based fixes when LLM is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from selfrepair.analyzers.space_analyzer import SpaceDiagnosis, analyze_space
from selfrepair.llm.ollabridge_client import OllaBridgeClient
from selfrepair.models import RepoHealthReport
from selfrepair.settings import Settings

logger = logging.getLogger(__name__)

# ---- Prompt templates ----

SPACE_REPAIR_SYSTEM = """You are an expert HuggingFace Spaces developer.
Your job is to analyze broken Spaces and generate complete, working fixes.
Always output valid JSON with the structure shown in the user prompt.
Use modern libraries: gradio>=4.0, diffusers, transformers, etc.
For GPU models, use @spaces.GPU decorator with ZeroGPU.
Keep apps self-contained and simple."""

SPACE_REPAIR_PROMPT = """A HuggingFace Space is broken and needs repair.

## Space Info
- Name: {space_name}
- Current SDK: {sdk}
- Current app_file: {app_file}
- Hardware: {hardware}
- Runtime stage: {runtime_stage}

## Issues Found
{issues}

## Dead Patterns Found
{dead_patterns}

## Current Files
{file_listing}

## Current app.py content (first 200 lines)
{app_content}

## Recommendations from analyzer
{recommendations}

Generate a complete fix as JSON:
{{
  "sdk": "gradio",
  "app_file": "app.py",
  "needs_gpu": true/false,
  "files": {{
    "app.py": "<complete new app.py content>",
    "requirements.txt": "<complete new requirements.txt>",
    "README.md": "<complete new README.md with YAML front matter>"
  }},
  "explanation": "<brief explanation of what was fixed and why>"
}}"""


def _build_file_listing(repo_dir: Path) -> str:
    """List key files in the Space repo."""
    lines = []
    for p in sorted(repo_dir.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            rel = p.relative_to(repo_dir)
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            lines.append(f"  {rel} ({size} bytes)")
    return "\n".join(lines[:50]) or "  (no files)"


def _read_app_content(repo_dir: Path, app_file: str, max_lines: int = 200) -> str:
    """Read the current app file content."""
    path = repo_dir / app_file
    if not path.exists():
        return "(file not found)"
    try:
        lines = path.read_text(errors="replace").splitlines()[:max_lines]
        return "\n".join(lines)
    except OSError:
        return "(read error)"


def _parse_llm_response(response: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    # Try direct JSON parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    # Try extracting from code block
    match = re.search(r"```(?:json)?\s*\n(.+?)\n```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding JSON object in text
    match = re.search(r"\{[^{}]*\"files\"[^{}]*\{.*?\}.*?\}", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def generate_llm_fix(
    diag: SpaceDiagnosis,
    report: RepoHealthReport,
    repo_dir: Path,
    ollabridge: OllaBridgeClient,
) -> dict[str, Any] | None:
    """Use OllaBridge LLM to generate a Space fix.

    Returns parsed JSON fix plan, or None if LLM fails.
    """
    prompt = SPACE_REPAIR_PROMPT.format(
        space_name=report.repo.full_name,
        sdk=diag.sdk,
        app_file=diag.app_file,
        hardware=diag.hardware,
        runtime_stage=diag.runtime_stage,
        issues="\n".join(f"- {i}" for i in diag.issues) or "(none detected)",
        dead_patterns="\n".join(f"- {p}" for p in diag.dead_patterns_found) or "(none)",
        file_listing=_build_file_listing(repo_dir),
        app_content=_read_app_content(repo_dir, diag.app_file),
        recommendations="\n".join(f"- {r}" for r in diag.recommendations) or "(none)",
    )

    try:
        response = ollabridge.chat(prompt, system=SPACE_REPAIR_SYSTEM)
        fix_plan = _parse_llm_response(response)
        if fix_plan and "files" in fix_plan:
            report.notes.append(f"LLM generated fix: {fix_plan.get('explanation', 'no explanation')}")
            return fix_plan
        report.notes.append("LLM response did not contain valid fix JSON")
    except Exception as exc:
        logger.warning("LLM Space repair failed: %s", exc)
        report.notes.append(f"LLM repair failed: {exc}")
    return None


def generate_template_fix(
    diag: SpaceDiagnosis,
    report: RepoHealthReport,
    repo_dir: Path,
) -> dict[str, Any]:
    """Generate a template-based fix when LLM is unavailable.

    Creates a simple Gradio app that uses gradio_client to call
    a public Space, or a basic placeholder app.
    """
    space_name = report.repo.name
    title = space_name.replace("-", " ").replace("_", " ").title()

    if diag.needs_gpu:
        # GPU app template using diffusers + ZeroGPU
        app_content = f'''"""\n{title} - Powered by AI\nAuto-generated by RepoGuardian\n"""\nimport gradio as gr\nimport numpy as np\nimport torch\n\ntry:\n    import spaces\n    GPU_AVAILABLE = True\nexcept ImportError:\n    GPU_AVAILABLE = False\n\n\ndef process(prompt: str, progress=gr.Progress(track_tqdm=True)):\n    """Process the user request."""\n    if not prompt.strip():\n        raise gr.Error("Please enter a prompt.")\n    # Placeholder - replace with actual model inference\n    return f"Generated output for: {{prompt}}"\n\nif GPU_AVAILABLE:\n    process = spaces.GPU(process)\n\nwith gr.Blocks(theme=gr.themes.Soft(), title="{title}") as demo:\n    gr.Markdown("# {title}")\n    gr.Markdown("Enter your prompt below.")\n    with gr.Row():\n        with gr.Column():\n            prompt = gr.Textbox(label="Prompt", lines=3)\n            btn = gr.Button("Generate", variant="primary")\n        with gr.Column():\n            output = gr.Textbox(label="Output", lines=5)\n    btn.click(fn=process, inputs=[prompt], outputs=[output])\n\nif __name__ == "__main__":\n    demo.launch()\n'''
        requirements = "gradio>=4.0.0\ntorch>=2.0.0\nnumpy>=1.24.0\n"
    else:
        # CPU app template
        app_content = f'''"""\n{title} - Powered by AI\nAuto-generated by RepoGuardian\n"""\nimport gradio as gr\n\n\ndef process(text: str):\n    """Process the user input."""\n    if not text.strip():\n        raise gr.Error("Please enter some text.")\n    return f"Processed: {{text}}"\n\n\nwith gr.Blocks(theme=gr.themes.Soft(), title="{title}") as demo:\n    gr.Markdown("# {title}")\n    gr.Markdown("Enter your input below.")\n    with gr.Row():\n        inp = gr.Textbox(label="Input", lines=3)\n        out = gr.Textbox(label="Output", lines=3)\n    btn = gr.Button("Process", variant="primary")\n    btn.click(fn=process, inputs=[inp], outputs=[out])\n\nif __name__ == "__main__":\n    demo.launch()\n'''
        requirements = "gradio>=4.0.0\n"

    readme = f"""---\ntitle: {title}\nemoji: \U0001f680\ncolorFrom: blue\ncolorTo: purple\nsdk: gradio\nsdk_version: 5.23.0\napp_file: app.py\npinned: false\nlicense: apache-2.0\nshort_description: {title}\n---\n\n# {title}\n\nAuto-repaired by [RepoGuardian](https://github.com/ruslanmv/RepoGuardian).\n"""

    report.notes.append("Applied template-based fix (LLM unavailable)")
    return {
        "sdk": "gradio",
        "app_file": "app.py",
        "needs_gpu": diag.needs_gpu,
        "files": {
            "app.py": app_content,
            "requirements.txt": requirements,
            "README.md": readme,
        },
        "explanation": "Template-based fix: replaced broken app with working Gradio placeholder",
    }


def apply_space_fix(
    fix_plan: dict[str, Any],
    repo_dir: Path,
) -> list[str]:
    """Write fix files to the repo directory.

    Returns list of changed file paths.
    """
    changed = []
    files = fix_plan.get("files", {})
    for filename, content in files.items():
        filepath = repo_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        changed.append(filename)
        logger.info("Wrote fix file: %s (%d bytes)", filename, len(content))
    return changed


def heal_space(
    report: RepoHealthReport,
    repo_dir: Path,
    settings: Settings,
    runtime_info: dict[str, Any] | None = None,
) -> tuple[SpaceDiagnosis, list[str]]:
    """Full Space healing pipeline.

    1. Analyze the Space
    2. Generate fix (LLM or template)
    3. Apply fix files
    4. Return diagnosis and changed files

    Args:
        report: Health report to update.
        repo_dir: Cloned Space directory.
        settings: RepoGuardian settings.
        runtime_info: Optional HF API runtime info.

    Returns:
        Tuple of (diagnosis, list of changed files).
    """
    # Step 1: Analyze
    diag = analyze_space(report, repo_dir, runtime_info)
    if diag.is_healthy:
        report.notes.append("Space analysis: healthy, no repairs needed")
        return diag, []

    logger.info(
        "Space %s diagnosed: %s severity, %d issues",
        report.repo.full_name, diag.severity, len(diag.issues),
    )

    # Step 2: Generate fix
    fix_plan = None
    if settings.ollabridge_enabled:
        ollabridge = OllaBridgeClient(settings)
        if ollabridge.available():
            fix_plan = generate_llm_fix(diag, report, repo_dir, ollabridge)

    if fix_plan is None:
        fix_plan = generate_template_fix(diag, report, repo_dir)

    # Step 3: Apply fix
    changed = apply_space_fix(fix_plan, repo_dir)
    report.changed_files = sorted(set(report.changed_files + changed))

    return diag, changed
