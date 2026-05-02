import pytest
from pydantic import ValidationError

from selfrepair.config.repo_config import RepoConfig, load_repo_config


class TestRepoConfigDefaults:
    def test_defaults_are_safe(self) -> None:
        cfg = RepoConfig()
        assert cfg.auto_merge == []
        assert cfg.escalate_to_llm == []
        assert cfg.codeowners_required is True
        assert cfg.budget.monthly_usd == 0.0
        assert "migrations/**" in cfg.deny_paths
        assert "infra/prod/**" in cfg.deny_paths

    def test_no_llm_enabled_by_default(self) -> None:
        cfg = RepoConfig()
        assert not cfg.llm_enabled_for("any_kind")


class TestRepoConfigValidation:
    def test_unknown_top_level_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RepoConfig.model_validate({"version": 1, "unknown_key": True})

    def test_negation_pattern_in_deny_paths_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RepoConfig.model_validate({"version": 1, "deny_paths": ["!keep/**"]})

    def test_invalid_severity_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RepoConfig.model_validate(
                {
                    "version": 1,
                    "auto_merge": [
                        {"kind": "x", "severity": "super-critical"}
                    ],
                }
            )

    def test_max_iterations_bounded(self) -> None:
        with pytest.raises(ValidationError):
            RepoConfig.model_validate(
                {
                    "version": 1,
                    "escalate_to_llm": [
                        {"kind": "x", "max_iterations": 100}
                    ],
                }
            )


class TestRepoConfigQueries:
    def test_llm_enabled_for_returns_true_only_when_kind_listed(self) -> None:
        cfg = RepoConfig.model_validate(
            {"version": 1, "escalate_to_llm": [{"kind": "test_failure"}]}
        )
        assert cfg.llm_enabled_for("test_failure")
        assert not cfg.llm_enabled_for("makefile_missing")

    def test_llm_iterations_default_for_unknown_kind(self) -> None:
        cfg = RepoConfig()
        assert cfg.llm_iterations_for("anything") == 0

    def test_auto_merge_respects_severity_ceiling(self) -> None:
        cfg = RepoConfig.model_validate(
            {
                "version": 1,
                "auto_merge": [{"kind": "lockfile_bump", "severity": "low"}],
            }
        )
        assert cfg.auto_merge_for("lockfile_bump", "low") is not None
        assert cfg.auto_merge_for("lockfile_bump", "info") is not None
        assert cfg.auto_merge_for("lockfile_bump", "high") is None

    def test_auto_merge_for_unknown_kind_returns_none(self) -> None:
        cfg = RepoConfig.model_validate(
            {
                "version": 1,
                "auto_merge": [{"kind": "a", "severity": "high"}],
            }
        )
        assert cfg.auto_merge_for("b", "low") is None


class TestRepoConfigLoading:
    def test_load_returns_defaults_when_file_absent(self, tmp_path) -> None:
        cfg = load_repo_config(tmp_path)
        assert cfg == RepoConfig()

    def test_load_parses_yaml(self, tmp_path) -> None:
        (tmp_path / ".selfrepair.yml").write_text(
            "version: 1\nschedule: 'daily'\n", encoding="utf-8"
        )
        cfg = load_repo_config(tmp_path)
        assert cfg.schedule == "daily"

    def test_load_handles_empty_file(self, tmp_path) -> None:
        (tmp_path / ".selfrepair.yml").write_text("", encoding="utf-8")
        cfg = load_repo_config(tmp_path)
        assert cfg == RepoConfig()
