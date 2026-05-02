from __future__ import annotations

from selfrepair.git.pr_builder import PRBodyContext, render_pr_body
from selfrepair.sdk.models import Finding, RepairPlan, Severity


def _ctx(*, signed: bool = True) -> PRBodyContext:
    finding = Finding(
        kind="missing_makefile",
        severity=Severity.LOW,
        file_path="Makefile",
        rule_id="py.makefile",
    )
    plan = RepairPlan(
        fixer_id="py.makefile",
        finding=finding,
        summary="Add Makefile with install/test/start targets",
        risk=Severity.LOW,
        files_touched=("Makefile",),
    )
    return PRBodyContext(
        finding=finding,
        plan=plan,
        files_changed=("Makefile",),
        summary=plan.summary,
        rationale="The repo lacks a Makefile.",
        commit_sha="abc1234",
        provenance={
            "builder": "selfrepair",
            "run_id": "r1",
            "run_url": "http://example.com",
            "materials_hash": "h",
            "signed": signed,
        },
    )


class TestPRBody:
    def test_renders_summary(self) -> None:
        body = render_pr_body(_ctx())
        assert (
            "## SelfRepair: Add Makefile with install/test/start targets"
            in body
        )

    def test_includes_finding_kind_and_severity(self) -> None:
        body = render_pr_body(_ctx())
        assert "missing_makefile" in body
        assert "low" in body

    def test_lists_files_changed(self) -> None:
        body = render_pr_body(_ctx())
        assert "- `Makefile`" in body

    def test_includes_revert_command(self) -> None:
        body = render_pr_body(_ctx())
        assert "git revert abc1234" in body

    def test_signed_indicator(self) -> None:
        body = render_pr_body(_ctx(signed=True))
        assert "Sigstore" in body

    def test_unsigned_indicator(self) -> None:
        body = render_pr_body(_ctx(signed=False))
        assert "Unsigned" in body
