from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    # GitHub
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_org: str | None = Field(default=None, alias="GITHUB_ORG")
    github_user: str | None = Field(default=None, alias="GITHUB_USER")
    github_base_branch: str = Field(default="main", alias="GITHUB_BASE_BRANCH")
    github_include_private: bool = Field(default=True, alias="GITHUB_INCLUDE_PRIVATE")

    # GitLab
    gitlab_token: str | None = Field(default=None, alias="GITLAB_TOKEN")
    gitlab_url: str = Field(default="https://gitlab.com", alias="GITLAB_URL")
    gitlab_group: str | None = Field(default=None, alias="GITLAB_GROUP")
    gitlab_user: str | None = Field(default=None, alias="GITLAB_USER")
    gitlab_include_private: bool = Field(default=True, alias="GITLAB_INCLUDE_PRIVATE")

    # Hugging Face
    hf_token: str | None = Field(default=None, alias="HF_TOKEN")
    hf_namespace: str | None = Field(default=None, alias="HF_NAMESPACE")
    hf_repo_types: str = Field(default="model,dataset,space", alias="HF_REPO_TYPES")
    hf_auto_free_zerogpu: bool = Field(default=True, alias="HF_AUTO_FREE_ZEROGPU")
    hf_zerogpu_exclude: str = Field(default="", alias="HF_ZEROGPU_EXCLUDE")

    # Runtime
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    work_dir: Path = Field(default=Path("work"), alias="WORK_DIR")
    state_dir: Path = Field(default=Path("state"), alias="STATE_DIR")
    status_site_dir: Path = Field(default=Path("status-site"), alias="STATUS_SITE_DIR")
    max_fix_attempts: int = Field(default=2, alias="MAX_FIX_ATTEMPTS")
    repo_timeout_seconds: int = Field(default=300, alias="REPO_TIMEOUT_SECONDS")
    start_timeout_seconds: int = Field(default=45, alias="START_TIMEOUT_SECONDS")

    # GitPilot integration
    gitpilot_bin: str = Field(default="gitpilot", alias="GITPILOT_BIN")
    gitpilot_enabled: bool = Field(default=False, alias="GITPILOT_ENABLED")
    gitpilot_message_model: str | None = Field(default=None, alias="GITPILOT_MESSAGE_MODEL")

    # MatrixLab integration
    matrixlab_bin: str = Field(default="matrixlab", alias="MATRIXLAB_BIN")
    matrixlab_enabled: bool = Field(default=False, alias="MATRIXLAB_ENABLED")
    matrixlab_fallback_local: bool = Field(default=True, alias="MATRIXLAB_FALLBACK_LOCAL")
    matrixlab_api_url: str | None = Field(default=None, alias="MATRIXLAB_API_URL")

    # OllaBridge Cloud LLM integration.
    #
    # OllaBridge Cloud is the official enterprise LLM gateway for the
    # Agent-Matrix ecosystem. It speaks the OpenAI-compatible
    # /v1/chat/completions wire format, so callers that run SelfRepair as a
    # subprocess (notably matrix-maintainer) typically inject the standard
    # OPENAI_* env vars instead of the canonical OLLABRIDGE_* ones.
    #
    # Resolution order, highest precedence first:
    #   1. OLLABRIDGE_BASE_URL / OLLABRIDGE_API_KEY / OLLABRIDGE_MODEL
    #   2. OPENAI_BASE_URL     / OPENAI_API_KEY     / OPENAI_MODEL
    #   3. The built-in defaults below.
    #
    # The fallback is wired up in `_apply_openai_fallback` so the same
    # OpenAI-compatible code paths keep working unmodified. We also
    # auto-flip `ollabridge_enabled` to True when a key gets resolved
    # (matrix-maintainer subprocess flow does not set the boolean
    # explicitly -- having a key is operator intent enough).
    ollabridge_enabled: bool = Field(default=False, alias="OLLABRIDGE_ENABLED")
    ollabridge_base_url: str = Field(default="https://api.ollabridge.com/v1", alias="OLLABRIDGE_BASE_URL")
    ollabridge_api_key: str | None = Field(default=None, alias="OLLABRIDGE_API_KEY")
    ollabridge_model: str = Field(default="qwen2.5:1.5b", alias="OLLABRIDGE_MODEL")
    ollabridge_timeout: float = Field(default=120.0, alias="OLLABRIDGE_TIMEOUT")

    # Status site
    site_base_url: str | None = Field(default=None, alias="SITE_BASE_URL")
    site_title: str = Field(default="SelfRepair Repo", alias="SITE_TITLE")
    site_description: str = Field(default="Open-source AI Secure Delivery Copilot for scanning repositories, detecting delivery risks, generating AI-assisted repairs, validating fixes, and returning audit-ready reports.", alias="SITE_DESCRIPTION")

    # Policy
    allow_autofix_pr: bool = Field(default=False, alias="ALLOW_AUTOFIX_PR")
    allow_direct_push: bool = Field(default=False, alias="ALLOW_DIRECT_PUSH")
    max_autofix_files: int = Field(default=25, alias="MAX_AUTOFIX_FILES")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    clone_depth: int = Field(default=1, alias="CLONE_DEPTH")

    @model_validator(mode="after")
    def _apply_openai_fallback(self) -> Settings:
        """Fall back to OPENAI_* env vars when OLLABRIDGE_* are unset.

        matrix-maintainer and other Agent-Matrix subprocesses pass the
        OpenAI-compatible env vars (OPENAI_BASE_URL, OPENAI_API_KEY,
        OPENAI_MODEL) when spawning SelfRepair. We treat those as a
        compatibility alias for the canonical OLLABRIDGE_* names so the
        ecosystem can share a single configuration surface.

        We also auto-enable OllaBridge if a key was resolved but
        OLLABRIDGE_ENABLED was not explicitly set -- an injected API
        key is operator intent enough. An explicit
        ``OLLABRIDGE_ENABLED=false`` continues to win because the
        env-var binding has already run by the time this validator
        sees the model.
        """
        # Base URL: only override when caller did not set OLLABRIDGE_BASE_URL.
        if "OLLABRIDGE_BASE_URL" not in os.environ:
            openai_base = os.environ.get("OPENAI_BASE_URL")
            if openai_base:
                self.ollabridge_base_url = openai_base

        # API key: only override when caller did not set OLLABRIDGE_API_KEY.
        had_explicit_key = self.ollabridge_api_key is not None
        if not had_explicit_key:
            openai_key = os.environ.get("OPENAI_API_KEY")
            if openai_key:
                self.ollabridge_api_key = openai_key

        # Model: only override when caller did not set OLLABRIDGE_MODEL.
        if "OLLABRIDGE_MODEL" not in os.environ:
            openai_model = os.environ.get("OPENAI_MODEL")
            if openai_model:
                self.ollabridge_model = openai_model

        # Auto-enable on resolved key, unless the operator opted out.
        explicit_enabled = (
            "OLLABRIDGE_ENABLED" in os.environ or "OLLABRIDGE_ENABLED".lower() in os.environ
        )
        if not self.ollabridge_enabled and not explicit_enabled and self.ollabridge_api_key:
            self.ollabridge_enabled = True

        return self

    def ensure_directories(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.status_site_dir.mkdir(parents=True, exist_ok=True)
        (self.status_site_dir / "data").mkdir(parents=True, exist_ok=True)

    @property
    def hf_repo_type_list(self) -> list[str]:
        return [item.strip() for item in self.hf_repo_types.split(",") if item.strip()]

    @property
    def hf_zerogpu_exclude_set(self) -> set[str]:
        return {s.strip() for s in self.hf_zerogpu_exclude.split(",") if s.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
