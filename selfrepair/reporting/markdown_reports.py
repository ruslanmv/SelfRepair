from selfrepair.models import RepoHealthReport

def render_markdown_summary(reports: list[RepoHealthReport]) -> str:
    lines = ["# Daily Repo Health", ""]
    for report in reports:
        lines.append(f"- **{report.repo.full_name}** \u2014 {report.status}")
    return "\n".join(lines) + "\n"
