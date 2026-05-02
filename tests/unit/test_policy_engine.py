from __future__ import annotations

import pytest

from selfrepair.config.repo_config import RepoConfig
from selfrepair.policy import (
    PolicyContext,
    PolicyOutcome,
    default_engine,
)
from selfrepair.policy.glob import matches
from selfrepair.policy.rules.budget import budget_rule
from selfrepair.policy.rules.codeowners import codeowners_rule
from selfrepair.policy.rules.paths import deny_paths_rule
from selfrepair.policy.rules.risk import risk_rule
from selfrepair.sdk.models import Finding, RepairPlan, Severity


def _ctx(
    *,
    finding: Finding | None = None,
    plan: RepairPlan | None = None,
    repo_config: RepoConfig | None = None,
    files_changed: tuple[str, ...] = ("src/foo.py",),
    is_llm_repair: bool = False,
    estimated_cost_usd: float = 0.0,
    spent_this_month_usd: float = 0.0,
) -> PolicyContext:
    finding = finding or Finding(
        kind="test_kind",
        severity=Severity.LOW,
        file_path="src/foo.py",
    )
    plan = plan or RepairPlan(
        fixer_id="test_fixer",
        finding=finding,
        summary="test plan",
        risk=Severity.LOW,
        files_touched=("src/foo.py",),
    )
    return PolicyContext(
        finding=finding,
        plan=plan,
        repo_config=repo_config or RepoConfig(),
        files_changed=files_changed,
        is_llm_repair=is_llm_repair,
        estimated_cost_usd=estimated_cost_usd,
        spent_this_month_usd=spent_this_month_usd,
    )


class TestGlobMatches:
    @pytest.mark.parametrize(
        "path,pattern,expected",
        [
            ("a.py", "a.py", True),
            ("a.py", "*.py", True),
            ("a/b.py", "a/*.py", True),
            ("a/b/c.py", "a/*.py", False),
            ("a/b/c.py", "a/**", True),
            ("a/b/c.py", "a/**/c.py", True),
            ("infra/prod/k8s/deployment.yaml", "infra/prod/**", True),
            ("infra/dev/k8s/deployment.yaml", "infra/prod/**", False),
            ("migrations/0001.py", "migrations/**", True),
            ("src/migrations/0001.py", "migrations/**", False),
        ],
    )
    def test_matches(self, path: str, pattern: str, expected: bool) -> None:
        assert matches(path, pattern) is expected


class TestDenyPathsRule:
    def test_allows_paths_outside_deny_list(self) -> None:
        ctx = _ctx(files_changed=("src/foo.py",))
        assert deny_paths_rule(ctx) is None

    def test_denies_path_matching_pattern(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "deny_paths": ["migrations/**"]}
        )
        ctx = _ctx(repo_config=config, files_changed=("migrations/0001.py",))
        decision = deny_paths_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.DENY
        assert "migrations" in decision.reason

    def test_denies_deep_glob_match(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "deny_paths": ["infra/prod/**"]}
        )
        ctx = _ctx(
            repo_config=config,
            files_changed=("infra/prod/k8s/deployment.yaml",),
        )
        assert deny_paths_rule(ctx) is not None


class TestBudgetRule:
    def test_skips_for_deterministic_repair(self) -> None:
        ctx = _ctx(is_llm_repair=False)
        assert budget_rule(ctx) is None

    def test_denies_when_no_budget_set(self) -> None:
        ctx = _ctx(is_llm_repair=True)
        decision = budget_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.DENY
        assert "budget is 0" in decision.reason

    def test_denies_when_projected_exceeds_cap(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "budget": {"monthly_usd": 10.0}}
        )
        ctx = _ctx(
            is_llm_repair=True,
            repo_config=config,
            estimated_cost_usd=2.0,
            spent_this_month_usd=9.0,
        )
        decision = budget_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.DENY

    def test_allows_when_under_cap(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "budget": {"monthly_usd": 10.0}}
        )
        ctx = _ctx(
            is_llm_repair=True,
            repo_config=config,
            estimated_cost_usd=2.0,
            spent_this_month_usd=5.0,
        )
        assert budget_rule(ctx) is None


class TestRiskRule:
    def test_high_risk_requires_review(self) -> None:
        plan = RepairPlan(
            fixer_id="x",
            finding=Finding(
                kind="k", severity=Severity.LOW, file_path="x.py"
            ),
            summary="s",
            risk=Severity.HIGH,
            files_touched=("x.py",),
        )
        ctx = _ctx(plan=plan)
        decision = risk_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.REVIEW
        assert decision.requires_approval

    def test_low_risk_passes(self) -> None:
        ctx = _ctx()
        assert risk_rule(ctx) is None

    def test_llm_without_opt_in_is_denied(self) -> None:
        finding = Finding(
            kind="test_failure", severity=Severity.LOW, file_path="x.py"
        )
        ctx = _ctx(finding=finding, is_llm_repair=True)
        decision = risk_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.DENY

    def test_llm_with_opt_in_passes(self) -> None:
        config = RepoConfig.model_validate(
            {
                "version": 1,
                "escalate_to_llm": [{"kind": "test_failure"}],
            }
        )
        finding = Finding(
            kind="test_failure", severity=Severity.LOW, file_path="x.py"
        )
        ctx = _ctx(finding=finding, repo_config=config, is_llm_repair=True)
        assert risk_rule(ctx) is None


class TestCodeownersRule:
    def test_required_emits_review(self) -> None:
        ctx = _ctx()  # default codeowners_required=True
        decision = codeowners_rule(ctx)
        assert decision is not None
        assert decision.outcome == PolicyOutcome.REVIEW
        assert decision.requires_approval

    def test_disabled_skips(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "codeowners_required": False}
        )
        ctx = _ctx(repo_config=config)
        assert codeowners_rule(ctx) is None

    def test_no_files_changed_skips(self) -> None:
        ctx = _ctx(files_changed=())
        assert codeowners_rule(ctx) is None


class TestEngineComposition:
    def test_first_non_allow_wins_deny_paths(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "deny_paths": ["migrations/**"]}
        )
        ctx = _ctx(
            repo_config=config, files_changed=("migrations/0001.py",)
        )
        decision = default_engine().evaluate(ctx)
        assert decision.outcome == PolicyOutcome.DENY
        assert decision.rule_id == "deny_paths"

    def test_all_pass_returns_allow(self) -> None:
        config = RepoConfig.model_validate(
            {"version": 1, "codeowners_required": False}
        )
        ctx = _ctx(repo_config=config)
        decision = default_engine().evaluate(ctx)
        assert decision.outcome == PolicyOutcome.ALLOW
        assert decision.rule_id == "default"

    def test_codeowners_kicks_in_when_no_other_rule_fires(self) -> None:
        # Default config: codeowners_required=True. Should produce REVIEW.
        ctx = _ctx()
        decision = default_engine().evaluate(ctx)
        assert decision.outcome == PolicyOutcome.REVIEW
        assert decision.rule_id == "codeowners.required"
