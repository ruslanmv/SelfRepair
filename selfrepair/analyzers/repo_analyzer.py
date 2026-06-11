from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from selfrepair.models import RepoHealthReport, StandardCheck
from selfrepair.standards.python311_rules import ensure_python311
from selfrepair.standards.uv_rules import ensure_uv


def detect_repo_type(repo_dir: Path, platform: str) -> str:
    if platform == "huggingface":
        if (repo_dir / "app.py").exists() or (repo_dir / "requirements.txt").exists():
            return "space"
        if (repo_dir / "dataset_infos.json").exists() or (repo_dir / "data").exists():
            return "dataset"
        return "model"
    if (repo_dir / "package.json").exists():
        return "node"
    if (repo_dir / "pyproject.toml").exists() or (repo_dir / "requirements.txt").exists():
        return "python"
    return "generic"


def analyze_repo_layout(report: RepoHealthReport, repo_dir: Path) -> RepoHealthReport:
    makefile = repo_dir / "Makefile"
    pyproject = repo_dir / "pyproject.toml"
    health_test = repo_dir / "tests" / "test_health.py"
    readme = repo_dir / "README.md"

    report.repo_type = detect_repo_type(repo_dir, report.repo.platform)
    report.makefile_ok = makefile.exists()
    report.pyproject_ok = pyproject.exists()
    report.health_test_ok = health_test.exists()
    report.python311_ok = ensure_python311(pyproject) if pyproject.exists() else False
    report.uv_ok = ensure_uv(pyproject) if pyproject.exists() else False
    report.metadata_ok = readme.exists()

    report.checks = [
        StandardCheck(name="makefile", ok=report.makefile_ok),
        StandardCheck(name="pyproject", ok=report.pyproject_ok),
        StandardCheck(name="health_test", ok=report.health_test_ok),
        StandardCheck(name="python311", ok=report.python311_ok),
        StandardCheck(name="uv", ok=report.uv_ok),
        StandardCheck(name="readme", ok=report.metadata_ok),
    ]

    # HuggingFace Space-specific checks. analyze_space appends to report.checks
    # in place; we don't need its return value here.
    if report.repo.platform == "huggingface" and report.repo_type == "space":
        from selfrepair.analyzers.space_analyzer import analyze_space
        analyze_space(report, repo_dir)

    return report


# ---------------------------------------------------------------------------
# Generic detector-based analyzer (first-wave Repository Maintenance product).
#
# This is the GENERIC, client-agnostic surface used by the `selfrepair-repo`
# scan/plan/repair commands. It DIAGNOSES a repository and emits issue dicts of
# shape {id, severity, description, recommended_action}. It NEVER writes code:
# GitPilot performs writes, MatrixLab validates, SelfRepair only reports.
# ---------------------------------------------------------------------------

# Severity vocabulary shared with risk classification / health scoring.
SEVERITY_WEIGHTS: dict[str, int] = {
    "info": 2,
    "low": 5,
    "medium": 12,
    "high": 25,
    "critical": 40,
}

# Maps a detector id to the file(s) a repair would touch. Used by the planner
# to DERIVE allowed_paths from detected issues.
RECOMMENDED_FILES: dict[str, list[str]] = {
    "missing-health-test": ["tests/test_health.py"],
    "missing-pyproject": ["pyproject.toml"],
    "missing-license": ["LICENSE"],
    "missing-ci-workflow": [".github/workflows/**"],
    "broken-readme-links": ["README.md"],
    "missing-makefile-targets": ["Makefile"],
    "missing-hf-space-metadata": ["README.md"],
}


@dataclass
class Issue:
    """A single detected repository problem."""

    id: str
    severity: str
    description: str
    recommended_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "severity": self.severity,
            "description": self.description,
            "recommended_action": self.recommended_action,
        }


@dataclass
class AnalysisResult:
    """Aggregated detector output for a repository."""

    repo_path: Path
    issues: list[Issue] = field(default_factory=list)

    @property
    def issue_dicts(self) -> list[dict[str, str]]:
        return [i.to_dict() for i in self.issues]


# -- individual detectors ---------------------------------------------------

# Common health-test filenames we accept as "present".
_HEALTH_TEST_CANDIDATES = (
    "tests/test_health.py",
    "tests/test_healthcheck.py",
    "test/test_health.py",
    "tests/health_test.py",
)

_COMMON_MAKE_TARGETS = ("install", "test", "lint")


def detect_missing_health_test(repo_dir: Path) -> Issue | None:
    for candidate in _HEALTH_TEST_CANDIDATES:
        if (repo_dir / candidate).exists():
            return None
    # Also accept any file under tests/ that looks like a health test.
    tests_dir = repo_dir / "tests"
    if tests_dir.is_dir():
        for p in tests_dir.rglob("*health*.py"):
            if p.is_file():
                return None
    return Issue(
        id="missing-health-test",
        severity="medium",
        description="No health test found (e.g. tests/test_health.py).",
        recommended_action="Add tests/test_health.py asserting the package imports and core invariants hold.",
    )


def detect_missing_pyproject(repo_dir: Path) -> Issue | None:
    if (repo_dir / "pyproject.toml").exists():
        return None
    return Issue(
        id="missing-pyproject",
        severity="high",
        description="No pyproject.toml found at the repository root.",
        recommended_action="Add a pyproject.toml declaring build-system, project metadata and dependencies.",
    )


def detect_missing_license(repo_dir: Path) -> Issue | None:
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        if (repo_dir / name).exists():
            return None
    return Issue(
        id="missing-license",
        severity="medium",
        description="No LICENSE file found at the repository root.",
        recommended_action="Add a LICENSE file (e.g. Apache-2.0 or MIT) declaring the project license.",
    )


def detect_missing_ci_workflow(repo_dir: Path) -> Issue | None:
    workflows = repo_dir / ".github" / "workflows"
    if workflows.is_dir():
        for p in workflows.iterdir():
            if p.suffix in (".yml", ".yaml"):
                return None
    return Issue(
        id="missing-ci-workflow",
        severity="medium",
        description="No CI workflow found under .github/workflows/.",
        recommended_action="Add a GitHub Actions workflow under .github/workflows/ that installs deps and runs tests.",
    )


def _markdown_links(text: str) -> list[tuple[str, str]]:
    """Return (label, target) pairs for markdown links in *text*."""
    return re.findall(r"\[([^\]]*)\]\(([^)]+)\)", text)


def detect_broken_readme_links(repo_dir: Path, check_network: bool = False) -> Issue | None:
    """Detect broken README links.

    Network-optional: relative links to non-existent files are always checked.
    http(s) links are only fetched when *check_network* is True.
    """
    readme = None
    for name in ("README.md", "Readme.md", "readme.md"):
        candidate = repo_dir / name
        if candidate.exists():
            readme = candidate
            break
    if readme is None:
        return None  # missing README is not this detector's concern

    text = readme.read_text(encoding="utf-8", errors="replace")
    broken: list[str] = []
    for _label, target in _markdown_links(text):
        target = target.strip()
        if not target or target.startswith("#") or target.startswith("mailto:"):
            continue
        if target.startswith("http://") or target.startswith("https://"):
            if check_network:
                try:
                    import httpx

                    resp = httpx.head(target, follow_redirects=True, timeout=5)
                    if resp.status_code >= 400:
                        broken.append(target)
                except Exception:
                    broken.append(target)
            continue
        # Relative link -> resolve against repo root and check existence.
        rel = target.split("#", 1)[0].split("?", 1)[0]
        if not rel:
            continue
        if not (readme.parent / rel).exists() and not (repo_dir / rel).exists():
            broken.append(target)

    if not broken:
        return None
    return Issue(
        id="broken-readme-links",
        severity="low",
        description=f"README contains {len(broken)} broken link(s): {', '.join(broken[:5])}.",
        recommended_action="Fix or remove the broken README links so all referenced files/URLs resolve.",
    )


def detect_missing_makefile_targets(
    repo_dir: Path, required: tuple[str, ...] = _COMMON_MAKE_TARGETS
) -> Issue | None:
    makefile = None
    for name in ("Makefile", "makefile", "GNUmakefile"):
        candidate = repo_dir / name
        if candidate.exists():
            makefile = candidate
            break
    if makefile is None:
        return Issue(
            id="missing-makefile-targets",
            severity="low",
            description="No Makefile found; common developer targets are unavailable.",
            recommended_action=f"Add a Makefile with targets: {', '.join(required)}.",
        )
    text = makefile.read_text(encoding="utf-8", errors="replace")
    present = set(re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*:", text))
    missing = [t for t in required if t not in present]
    if not missing:
        return None
    return Issue(
        id="missing-makefile-targets",
        severity="low",
        description=f"Makefile is missing common target(s): {', '.join(missing)}.",
        recommended_action=f"Add the following Makefile target(s): {', '.join(missing)}.",
    )


def detect_missing_hf_space_metadata(repo_dir: Path) -> Issue | None:
    """Detect a Hugging Face Space missing README front-matter.

    Only fires when the repo looks like an HF Space (app.py + requirements.txt
    or a Space-style file) but the README lacks YAML front-matter.
    """
    looks_like_space = (repo_dir / "app.py").exists() and (
        (repo_dir / "requirements.txt").exists() or (repo_dir / "packages.txt").exists()
    )
    if not looks_like_space:
        return None
    readme = repo_dir / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="replace").lstrip()
        if text.startswith("---"):
            # Has front-matter; check for an sdk key as a minimal validity gate.
            front = text.split("---", 2)
            if len(front) >= 3 and "sdk" in front[1]:
                return None
    return Issue(
        id="missing-hf-space-metadata",
        severity="medium",
        description="Repository looks like a Hugging Face Space but README lacks valid front-matter (sdk/app_file).",
        recommended_action="Add YAML front-matter to README.md declaring the HF Space sdk, app_file and title.",
    )


# Detector registry. Order is stable so output / allowed_paths are deterministic.
_DETECTORS = (
    detect_missing_health_test,
    detect_missing_pyproject,
    detect_missing_license,
    detect_missing_ci_workflow,
    detect_broken_readme_links,
    detect_missing_makefile_targets,
    detect_missing_hf_space_metadata,
)


def run_detectors(repo_dir: Path, check_network: bool = False) -> list[Issue]:
    """Run every detector against *repo_dir* and collect issues."""
    issues: list[Issue] = []
    for detector in _DETECTORS:
        try:
            if detector is detect_broken_readme_links:
                issue = detector(repo_dir, check_network=check_network)
            else:
                issue = detector(repo_dir)
        except Exception:
            issue = None
        if issue is not None:
            issues.append(issue)
    return issues


def analyze_path(repo_dir: str | Path, check_network: bool = False) -> AnalysisResult:
    """Analyze a local repository path and return aggregated issues."""
    path = Path(repo_dir)
    return AnalysisResult(repo_path=path, issues=run_detectors(path, check_network))


def _shallow_clone(repo_url: str, branch: str, dest: Path) -> bool:
    """Best-effort shallow clone. Returns True on success, False on failure."""
    cmd = ["git", "clone", "--depth=1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo_url, str(dest)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception:
        return False


def analyze_repo(
    repo: str | Path,
    branch: str = "main",
    check_network: bool = False,
) -> AnalysisResult:
    """Analyze a repository given a local path or a clone URL.

    - Local path: analyzed in place.
    - URL: a shallow clone is attempted; on failure (offline/unreachable) the
      analysis degrades to an empty result so dry-run flows still complete.
    """
    candidate = Path(str(repo))
    if candidate.exists() and candidate.is_dir():
        return analyze_path(candidate, check_network=check_network)

    # Treat as a remote URL: shallow clone into a temp dir.
    tmp = Path(tempfile.mkdtemp(prefix="selfrepair-clone-"))
    dest = tmp / "repo"
    if _shallow_clone(str(repo), branch, dest):
        return analyze_path(dest, check_network=check_network)
    # Degrade gracefully when offline / unreachable.
    return AnalysisResult(repo_path=candidate, issues=[])
