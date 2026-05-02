"""Issue Watch — sync, classify, and act on external human-created issues
from GitHub Issues, GitLab Issues, and Hugging Face Community Discussions.

The package is structured for a single seam to the existing pipeline:
external issues become normal SelfRepair jobs (`JobTrigger.ISSUE`) routed
through the same clone/analyze/scan/plan/repair/validate/publish stages.

Module map:
    schemas        — provider-neutral DTOs (ExternalIssueDTO, IssueComment)
    fingerprints   — stable cross-provider fingerprint
    classifier     — deterministic-first repair-class assignment
    policies       — never-auto-repair set + repairability decision
    clients        — IssueProviderClient Protocol + factory
    github_client  — GitHub Issues REST adapter
    gitlab_client  — GitLab Issues REST adapter
    huggingface_client — HF Community Discussions adapter
    service        — orchestration: fetch -> classify -> upsert -> reconcile
    sync           — Arq worker task + scheduled cron entry
    dispatcher     — webhook -> dispatch routing (GitHub `issues`/`issue_comment`,
                     GitLab `Issue Hook`/`Note Hook`)
    config         — runtime knobs (kill switch, sync window, page size)

The package is intentionally additive. Importing it has no side effects;
configure it via `SELFREPAIR_*` env vars and it stays inert until the
worker registers `sync_external_issues` or the API routes call into it.
"""

__all__ = [
    "FailureClass",
    "ISSUE_NEVER_AUTO_REPAIR",
    "Repairability",
    "classify_issue",
    "compute_fingerprint",
    "decide_repairability",
]

from selfrepair.issues.classifier import FailureClass, classify_issue
from selfrepair.issues.fingerprints import compute_fingerprint
from selfrepair.issues.policies import (
    ISSUE_NEVER_AUTO_REPAIR,
    Repairability,
    decide_repairability,
)
