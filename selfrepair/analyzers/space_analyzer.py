"""HuggingFace Space health analyzer.

Detects common issues in HF Spaces:
- Dead backend dependencies
- Outdated SDK versions
- Missing requirements.txt
- Wrong app_file in README metadata
- Hardware mismatches (CPU for GPU models)
- Runtime errors and build failures
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from selfrepair.models import RepoHealthReport, StandardCheck

logger = logging.getLogger(__name__)

# Known dead or deprecated patterns
DEAD_PATTERNS = [
    (r'st\.secrets\[.*BACKEND_SERVER.*\]', 'Dead backend server dependency'),
    (r'api-inference\.huggingface\.co', 'Deprecated HF Inference API endpoint (use router.huggingface.co)'),
    (r'from\s+dalle_mini', 'Deprecated dalle-mini imports'),
    (r'from\s+min_dalle', 'Deprecated min-dalle imports'),
    (r'from\s+transformers\.file_utils', 'Removed transformers.file_utils (use transformers.utils)'),
    (r'jax\.experimental\.PartitionSpec', 'Moved JAX PartitionSpec API'),
]

# SDK identifiers in README front matter
SDK_PATTERN = re.compile(r'^sdk:\s*(\S+)', re.MULTILINE)
APP_FILE_PATTERN = re.compile(r'^app_file:\s*(\S+)', re.MULTILINE)
SDK_VERSION_PATTERN = re.compile(r'^sdk_version:\s*(\S+)', re.MULTILINE)


@dataclass
class SpaceDiagnosis:
    """Diagnosis result for a HuggingFace Space."""
    sdk: str = "unknown"
    app_file: str = ""
    sdk_version: str = ""
    hardware: str = "cpu-basic"
    runtime_stage: str = "unknown"
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    dead_patterns_found: list[str] = field(default_factory=list)
    needs_gpu: bool = False
    needs_rebuild: bool = False
    severity: str = "info"  # info, warning, critical

    @property
    def is_healthy(self) -> bool:
        return self.severity == "info" and not self.issues


def parse_readme_metadata(readme_path: Path) -> dict[str, str]:
    """Extract YAML front matter from README.md."""
    if not readme_path.exists():
        return {}
    text = readme_path.read_text(errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    front = parts[1]
    meta: dict[str, str] = {}
    for m in [SDK_PATTERN, APP_FILE_PATTERN, SDK_VERSION_PATTERN]:
        match = m.search(front)
        if match:
            key = m.pattern.split(r":\s*")[0].lstrip("^")
            meta[key] = match.group(1)
    return meta


def scan_for_dead_patterns(repo_dir: Path) -> list[tuple[str, str]]:
    """Scan Python files for known dead/deprecated patterns."""
    found = []
    for py_file in repo_dir.rglob("*.py"):
        try:
            content = py_file.read_text(errors="replace")
        except OSError:
            continue
        for pattern, description in DEAD_PATTERNS:
            if re.search(pattern, content):
                rel = py_file.relative_to(repo_dir)
                found.append((str(rel), description))
    return found


def check_requirements(repo_dir: Path) -> list[str]:
    """Check requirements.txt for issues."""
    issues = []
    req_file = repo_dir / "requirements.txt"
    if not req_file.exists():
        issues.append("Missing requirements.txt")
        return issues
    content = req_file.read_text(errors="replace")
    if not content.strip():
        issues.append("Empty requirements.txt")
    return issues


def check_app_file(repo_dir: Path, meta: dict[str, str]) -> list[str]:
    """Verify app_file exists and is valid."""
    issues = []
    app_file = meta.get("app_file", "app.py")
    app_path = repo_dir / app_file
    if not app_path.exists():
        issues.append(f"app_file '{app_file}' does not exist")
    return issues


def detect_gpu_requirement(repo_dir: Path) -> bool:
    """Check if the Space needs GPU hardware."""
    gpu_indicators = [
        "torch", "diffusers", "transformers", "accelerate",
        "spaces.GPU", "@spaces.GPU", "cuda", ".to(\"cuda\")",
        "bitsandbytes", "auto_gptq", "vllm",
    ]
    for py_file in repo_dir.rglob("*.py"):
        try:
            content = py_file.read_text(errors="replace")
        except OSError:
            continue
        for indicator in gpu_indicators:
            if indicator in content:
                return True
    req_file = repo_dir / "requirements.txt"
    if req_file.exists():
        content = req_file.read_text(errors="replace")
        for indicator in gpu_indicators[:6]:
            if indicator in content:
                return True
    return False


def analyze_space(
    report: RepoHealthReport,
    repo_dir: Path,
    runtime_info: dict[str, Any] | None = None,
) -> SpaceDiagnosis:
    """Full diagnosis of a HuggingFace Space.

    Args:
        report: Current health report for the repo.
        repo_dir: Path to cloned Space repo.
        runtime_info: Optional runtime info from HF API (stage, hardware, etc).

    Returns:
        SpaceDiagnosis with issues, recommendations, and severity.
    """
    diag = SpaceDiagnosis()

    # Parse README metadata
    meta = parse_readme_metadata(repo_dir / "README.md")
    diag.sdk = meta.get("sdk", "unknown")
    diag.app_file = meta.get("app_file", "app.py")
    diag.sdk_version = meta.get("sdk_version", "")

    # Runtime info from HF API
    if runtime_info:
        diag.hardware = runtime_info.get("hardware", {}).get("current", "cpu-basic") or "cpu-basic"
        diag.runtime_stage = runtime_info.get("stage", "unknown")
        if diag.runtime_stage in ("RUNTIME_ERROR", "BUILD_ERROR"):
            diag.issues.append(f"Space is in {diag.runtime_stage} state")
            diag.severity = "critical"
            diag.needs_rebuild = True

    # Check app_file exists
    app_issues = check_app_file(repo_dir, meta)
    for issue in app_issues:
        diag.issues.append(issue)
        diag.severity = "critical"
        diag.needs_rebuild = True

    # Check requirements
    req_issues = check_requirements(repo_dir)
    for issue in req_issues:
        diag.issues.append(issue)
        if diag.severity != "critical":
            diag.severity = "warning"

    # Scan for dead patterns
    dead = scan_for_dead_patterns(repo_dir)
    for filepath, description in dead:
        diag.dead_patterns_found.append(f"{filepath}: {description}")
        diag.issues.append(f"Dead pattern in {filepath}: {description}")
        diag.severity = "critical"
        diag.needs_rebuild = True

    # Check GPU requirements vs hardware
    diag.needs_gpu = detect_gpu_requirement(repo_dir)
    if diag.needs_gpu and diag.hardware == "cpu-basic":
        diag.issues.append("Space requires GPU but running on cpu-basic")
        diag.recommendations.append("Request ZeroGPU (zero-a10g) hardware")
        if diag.severity != "critical":
            diag.severity = "warning"

    # Build recommendations
    if diag.needs_rebuild:
        diag.recommendations.append("Rebuild app.py with modern dependencies")
        if diag.sdk == "streamlit":
            diag.recommendations.append("Consider migrating to Gradio SDK for better HF integration")
    if not meta.get("sdk"):
        diag.recommendations.append("Add SDK metadata to README.md front matter")
    if diag.dead_patterns_found:
        diag.recommendations.append("Remove deprecated API calls and update to current versions")

    # Update the health report with Space-specific checks
    report.checks.extend([
        StandardCheck(name="space_sdk", ok=diag.sdk != "unknown", details=f"SDK: {diag.sdk}"),
        StandardCheck(name="space_app_file", ok=not app_issues, details=diag.app_file),
        StandardCheck(name="space_requirements", ok=not req_issues, details="requirements.txt"),
        StandardCheck(name="space_dead_patterns", ok=not dead, details=f"{len(dead)} dead patterns"),
        StandardCheck(name="space_hardware", ok=not (diag.needs_gpu and diag.hardware == "cpu-basic")),
    ])

    if diag.issues:
        report.notes.extend(diag.issues)

    return diag
