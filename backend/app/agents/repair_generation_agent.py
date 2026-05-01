from __future__ import annotations

from backend.app.schemas.issue import Issue
from backend.app.schemas.repair_patch import RepairPatch


class RepairGenerationAgent:
    """Generates safe repair suggestions and Bob-ready prompts.

    In production this can call IBM Bob or another approved coding assistant.
    The default open-source implementation is deterministic and dry-run safe:
    it describes the files SelfRepair's local repair engine can create/update.
    """

    def run(self, issues: list[Issue]) -> list[RepairPatch]:
        patches: list[RepairPatch] = []
        for issue in issues:
            if issue.check_name == "makefile":
                patches.append(_patch("Makefile", "create", "Create standard install/test/start targets", issue))
            elif issue.check_name == "pyproject":
                patches.append(_patch("pyproject.toml", "create", "Create Python 3.11 packaging metadata", issue))
            elif issue.check_name == "health_test":
                patches.append(_patch("tests/test_health.py", "create", "Create minimal smoke health test", issue))
            elif issue.check_name == "readme":
                patches.append(_patch("README.md", "create", "Create basic setup and validation documentation", issue))
            else:
                patches.append(_patch("repository", "suggest", issue.recommendation or issue.title, issue))
        return patches


def _patch(file_path: str, action: str, summary: str, issue: Issue) -> RepairPatch:
    prompt = (
        "Use IBM Bob to generate a safe repository repair. "
        f"Issue: {issue.title}. Recommendation: {issue.recommendation or summary}. "
        "Preserve existing behavior, prefer minimal changes, and include tests when possible."
    )
    return RepairPatch(
        file_path=file_path,
        action=action,  # type: ignore[arg-type]
        patch_summary=summary,
        safe_to_apply=True,
        generated_by="bob-ready-prompt",
        prompt=prompt,
    )
