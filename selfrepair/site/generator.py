"""Static status site generator."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from selfrepair.models import RepoHealthReport
from selfrepair.reporting.status_builder import build_summary
from selfrepair.settings import Settings


def generate_site(settings: Settings) -> None:
    """
    Generate the static status dashboard from latest status data.

    Args:
        settings: Application settings containing paths
    """
    # Ensure output directories exist
    data_dir = settings.status_site_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Read latest status
    latest_status_path = settings.state_dir / "latest_status.json"
    if not latest_status_path.exists():
        # Create empty status if it doesn't exist
        reports = []
    else:
        with open(latest_status_path, encoding="utf-8") as f:
            data = json.load(f)
            reports = [RepoHealthReport(**item) for item in data.get("items", [])]

    # Build summary
    summary = build_summary(
        title="Repository Health Dashboard",
        description="Automated repository health monitoring and repair status",
        reports=reports,
    )

    # Write summary.json
    summary_path = data_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(mode="json"), f, indent=2)

    # Write repos.json
    repos_path = data_dir / "repos.json"
    repos_data = {
        "items": [report.model_dump(mode="json") for report in reports],
        "total": len(reports),
    }
    with open(repos_path, "w", encoding="utf-8") as f:
        json.dump(repos_data, f, indent=2)

    # Copy static assets if they exist in the template
    template_dir = Path(__file__).parent.parent.parent / "status-site"
    if template_dir.exists():
        # Copy HTML templates
        for html_file in template_dir.glob("*.html"):
            shutil.copy2(html_file, settings.status_site_dir / html_file.name)

        # Copy assets directory
        assets_src = template_dir / "assets"
        if assets_src.exists():
            assets_dst = settings.status_site_dir / "assets"
            if assets_dst.exists():
                shutil.rmtree(assets_dst)
            shutil.copytree(assets_src, assets_dst)
