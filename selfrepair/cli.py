from __future__ import annotations

import json
import logging

import typer
from rich.console import Console
from rich.table import Table

from selfrepair.inventory.huggingface_discovery import HuggingFaceDiscovery
from selfrepair.inventory.github_discovery import GitHubOrgDiscovery
from selfrepair.inventory.gitlab_discovery import GitLabDiscovery
from selfrepair.log_config import configure_logging
from selfrepair.main import check_single_repo, run_daily
from selfrepair.site.generator import generate_site
from selfrepair.settings import get_settings

app = typer.Typer(add_completion=False, help="SelfRepair Repo CLI – autonomous repo health & repair")
console = Console()
logger = logging.getLogger(__name__)


@app.callback()
def _callback() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command("discover")
def discover() -> None:
    """Discover repositories across all configured platforms."""
    settings = get_settings()
    repos = (
        GitHubOrgDiscovery(settings).list_repositories()
        + HuggingFaceDiscovery(settings).list_repositories()
        + GitLabDiscovery(settings).list_repositories()
    )
    table = Table(title="Repositories")
    table.add_column("Platform")
    table.add_column("Name")
    table.add_column("Default branch")
    for repo in repos:
        table.add_row(repo.platform, repo.full_name, repo.default_branch)
    console.print(table)


@app.command("run")
@app.command("run-daily")
def run_daily_cmd() -> None:
    """Run full health check and repair cycle."""
    settings = get_settings()
    reports = run_daily(settings)
    console.print(f"Processed {len(reports)} repositories")


@app.command("publish-site")
def publish_site() -> None:
    """Generate the static status dashboard."""
    settings = get_settings()
    generate_site(settings)
    console.print("Status site generated")


@app.command("check-repo")
def check_repo(repo_name: str) -> None:
    """Check a single repository by name."""
    settings = get_settings()
    repos = (
        GitHubOrgDiscovery(settings).list_repositories()
        + HuggingFaceDiscovery(settings).list_repositories()
        + GitLabDiscovery(settings).list_repositories()
    )
    repo = next((r for r in repos if r.name == repo_name or r.full_name == repo_name), None)
    if repo is None:
        raise typer.Exit(f"Repository not found: {repo_name}")
    report = check_single_repo(repo, settings)
    console.print_json(data=report.model_dump(mode="json"))


@app.command("check-url")
def check_url(
    repo_url: str = typer.Argument(..., help="Git clone URL, for example https://github.com/owner/repo.git"),
    branch: str = typer.Option("main", "--branch", help="Branch to clone"),
) -> None:
    """Check a single repository directly from a Git URL.

    This command is the easiest open-source entry point because it does
    not require configuring GitHub, GitLab, or Hugging Face discovery.
    """
    from backend.app.services.git_service import GitService

    settings = get_settings()
    repo = GitService().build_repo_ref(repo_url, branch)
    report = check_single_repo(repo, settings)
    console.print_json(data=report.model_dump(mode="json"))


@app.command("fix-space")
def fix_space(
    space_id: str = typer.Argument(..., help="HuggingFace Space ID (e.g. 'user/space-name')"),
    push: bool = typer.Option(False, "--push", help="Push fixes to the Space repo"),
    hardware: bool = typer.Option(False, "--hardware", help="Also manage ZeroGPU hardware"),
) -> None:
    """Analyze and fix a broken HuggingFace Space.

    Uses OllaBridge LLM (if enabled) to generate intelligent fixes,
    with template-based fallback. Optionally pushes fixes and manages
    ZeroGPU hardware allocation.

    Examples:
        selfrepair-repo fix-space ruslanmv/Logo-Creator
        selfrepair-repo fix-space ruslanmv/Logo-Creator --push --hardware
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from selfrepair.analyzers.space_analyzer import analyze_space
    from selfrepair.healing.space_healer import heal_space
    from selfrepair.models import RepoHealthReport, RepoRef

    settings = get_settings()
    parts = space_id.split("/")
    if len(parts) != 2:
        console.print("[red]Space ID must be in format 'user/space-name'[/red]")
        raise typer.Exit(1)
    namespace, name = parts

    # Fetch runtime info from HF API
    runtime_info = None
    try:
        from huggingface_hub import HfApi
        hf_api = HfApi(token=settings.hf_token)
        info = hf_api.space_info(space_id)
        if info.runtime:
            runtime_info = info.runtime.raw
        console.print(f"[cyan]Space found:[/cyan] {space_id}")
        console.print(f"  SDK: {info.sdk}, Stage: {info.runtime.stage if info.runtime else 'unknown'}")
    except Exception as exc:
        console.print(f"[yellow]Warning: Could not fetch Space info: {exc}[/yellow]")

    # Clone the Space
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / name
        clone_url = f"https://huggingface.co/spaces/{space_id}"
        if settings.hf_token:
            clone_url = f"https://user:{settings.hf_token}@huggingface.co/spaces/{space_id}"

        console.print(f"[cyan]Cloning {space_id}...[/cyan]")
        result = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(repo_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            console.print(f"[red]Clone failed: {result.stderr}[/red]")
            raise typer.Exit(1)

        # Build report
        repo_ref = RepoRef(
            name=name,
            full_name=space_id,
            clone_url=clone_url,
            platform="huggingface",
            kind="space",
            namespace=namespace,
            web_url=f"https://huggingface.co/spaces/{space_id}",
        )
        report = RepoHealthReport(repo=repo_ref)

        # Run Space healing
        console.print("[cyan]Analyzing Space...[/cyan]")
        diag, changed = heal_space(report, repo_dir, settings, runtime_info)

        # Display diagnosis
        console.print()
        if diag.issues:
            console.print("[bold red]Issues found:[/bold red]")
            for issue in diag.issues:
                console.print(f"  [red]\u2717[/red] {issue}")
        if diag.recommendations:
            console.print("[bold yellow]Recommendations:[/bold yellow]")
            for rec in diag.recommendations:
                console.print(f"  [yellow]\u2192[/yellow] {rec}")
        if changed:
            console.print(f"\n[bold green]Fixed {len(changed)} files:[/bold green]")
            for f in changed:
                console.print(f"  [green]\u2713[/green] {f}")

        # Push if requested
        if push and changed and settings.hf_token:
            console.print("\n[cyan]Pushing fixes...[/cyan]")
            cmds = [
                ["git", "add", "-A"],
                ["git", "commit", "-m", "fix: auto-repair by SelfRepair Repo"],
                ["git", "push", "origin", "main"],
            ]
            for cmd in cmds:
                r = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
                if r.returncode != 0:
                    console.print(f"[red]Git command failed: {' '.join(cmd)}\n{r.stderr}[/red]")
                    break
            else:
                console.print("[green]Fixes pushed successfully![/green]")
                report.pushed_branch = "main"

        # Hardware management
        if hardware and diag.needs_gpu and settings.hf_token:
            console.print("\n[cyan]Managing hardware...[/cyan]")
            try:
                from selfrepair.inventory.hf_hardware import request_zerogpu
                success, hw_report = request_zerogpu(
                    hf_api, space_id, namespace,
                    auto_free=settings.hf_auto_free_zerogpu,
                    exclude=settings.hf_zerogpu_exclude_set,
                )
                if success:
                    console.print("[green]ZeroGPU assigned![/green]")
                    if hw_report.freed_slots:
                        console.print(f"  Freed slot: {hw_report.freed_slots[0]}")
                else:
                    for err in hw_report.errors:
                        console.print(f"[red]{err}[/red]")
            except Exception as exc:
                console.print(f"[red]Hardware management failed: {exc}[/red]")

        # Store diagnosis in report
        from selfrepair.models import SpaceDiagnosisResult
        report.space_diagnosis = SpaceDiagnosisResult(
            sdk=diag.sdk,
            app_file=diag.app_file,
            hardware=diag.hardware,
            runtime_stage=diag.runtime_stage,
            issues=diag.issues,
            recommendations=diag.recommendations,
            dead_patterns=diag.dead_patterns_found,
            needs_gpu=diag.needs_gpu,
            needs_rebuild=diag.needs_rebuild,
            severity=diag.severity,
            fix_applied=bool(changed),
            fix_explanation="\n".join(report.notes),
        )
        report.finalize_status()

        # Output report
        console.print(f"\n[bold]Status: {report.status}[/bold]")
        console.print_json(data=report.model_dump(mode="json"))


if __name__ == "__main__":
    app()
