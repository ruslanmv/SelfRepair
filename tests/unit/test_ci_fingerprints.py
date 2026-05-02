"""Fingerprints fold N flaky runs into one row.

These tests assert two design invariants:
  1. Two runs of the same flake produce the same fingerprint.
  2. Workflow-path-keyed input (not name-keyed) so a workflow rename
     doesn't reset history. Same path + signature → same fingerprint.
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")

from selfrepair.ci.fingerprints import (  # noqa: E402
    compute_fingerprint,
    normalize_signature,
)


class TestNormalizeSignature:
    def test_runner_path_collapses(self) -> None:
        a = normalize_signature(
            "/home/runner/work/proj/proj/src/x.py:42 KeyError: 'foo'"
        )
        b = normalize_signature(
            "/home/runner/work/other/other/src/x.py:99 KeyError: 'foo'"
        )
        assert "<runner>" in a
        assert "<runner>" in b
        assert a == b  # paths + line numbers normalised away

    def test_iso_timestamps_collapse(self) -> None:
        a = normalize_signature("2025-09-12T14:32:01Z connection refused")
        b = normalize_signature("2026-02-04T07:15:23Z connection refused")
        assert a == b

    def test_durations_collapse(self) -> None:
        a = normalize_signature("test_x failed after 12.4s")
        b = normalize_signature("test_x failed after 0.7s")
        assert a == b


class TestComputeFingerprint:
    def test_same_inputs_yield_same_fingerprint(self) -> None:
        kwargs = dict(
            repo_id="r1",
            workflow_path=".github/workflows/ci.yml",
            failed_job_name="test",
            failed_step_name="pytest",
            failure_class="test_failure",
            error_signature="AssertionError",
        )
        assert compute_fingerprint(**kwargs) == compute_fingerprint(**kwargs)

    def test_different_repo_yields_different_fingerprint(self) -> None:
        a = compute_fingerprint(
            repo_id="r1",
            workflow_path="ci.yml",
            failed_job_name="t",
            failed_step_name="s",
            failure_class="test_failure",
            error_signature="AssertionError",
        )
        b = compute_fingerprint(
            repo_id="r2",
            workflow_path="ci.yml",
            failed_job_name="t",
            failed_step_name="s",
            failure_class="test_failure",
            error_signature="AssertionError",
        )
        assert a != b

    def test_workflow_path_not_name_keyed(self) -> None:
        """Renaming the workflow's display name doesn't reset history."""
        common = dict(
            repo_id="r1",
            workflow_path=".github/workflows/ci.yml",
            failed_job_name="test",
            failed_step_name="pytest",
            failure_class="test_failure",
            error_signature="AssertionError",
        )
        # The fingerprint function takes `workflow_path` only — there's no
        # `workflow_name` argument — by construction. Smoke that the API
        # surface is path-keyed.
        fp = compute_fingerprint(**common)
        assert isinstance(fp, str)
        assert len(fp) == 32

    def test_empty_signature_falls_back_to_step(self) -> None:
        fp1 = compute_fingerprint(
            repo_id="r1",
            workflow_path="ci.yml",
            failed_job_name="t",
            failed_step_name="install",
            failure_class="missing_dependency",
            error_signature="",
        )
        fp2 = compute_fingerprint(
            repo_id="r1",
            workflow_path="ci.yml",
            failed_job_name="t",
            failed_step_name="install",
            failure_class="missing_dependency",
            error_signature="",
        )
        assert fp1 == fp2
