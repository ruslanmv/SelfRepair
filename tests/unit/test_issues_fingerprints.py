"""Stable fingerprints across re-syncs and provider mirrors.

Two design contracts:
  1. The same issue re-synced twice yields the same fingerprint.
  2. Cosmetic title rephrasings (tag prefixes, reopen tags) collapse.
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")

from selfrepair.issues.fingerprints import (  # noqa: E402
    compute_fingerprint,
    normalize_title,
)


class TestNormalizeTitle:
    def test_strips_tag_prefix(self) -> None:
        assert normalize_title("[BUG] CI fails on merge") == "ci fails on merge"

    def test_strips_trailing_paren_metadata(self) -> None:
        assert (
            normalize_title("CI fails on merge (reopened)")
            == "ci fails on merge"
        )

    def test_collapses_whitespace(self) -> None:
        assert normalize_title("  CI   fails  ") == "ci fails"

    def test_handles_empty(self) -> None:
        assert normalize_title("") == ""


class TestComputeFingerprint:
    def test_same_inputs_yield_same_fingerprint(self) -> None:
        kwargs = dict(
            repo_full_name="octo/x",
            title="CI fails on missing pyproject",
            provider_issue_id="42",
        )
        assert compute_fingerprint(**kwargs) == compute_fingerprint(**kwargs)

    def test_repo_change_changes_fingerprint(self) -> None:
        a = compute_fingerprint(
            repo_full_name="octo/x", title="t", provider_issue_id="1"
        )
        b = compute_fingerprint(
            repo_full_name="octo/y", title="t", provider_issue_id="1"
        )
        assert a != b

    def test_cosmetic_title_changes_collapse(self) -> None:
        a = compute_fingerprint(
            repo_full_name="octo/x",
            title="[BUG] CI fails on merge",
            provider_issue_id="42",
        )
        b = compute_fingerprint(
            repo_full_name="octo/x",
            title="CI fails on merge (reopened)",
            provider_issue_id="42",
        )
        assert a == b

    def test_fingerprint_is_32_hex_chars(self) -> None:
        fp = compute_fingerprint(
            repo_full_name="octo/x", title="t", provider_issue_id="1"
        )
        assert len(fp) == 32
        assert all(c in "0123456789abcdef" for c in fp)
