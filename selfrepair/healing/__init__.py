"""Healing engine: classify failures, plan and apply fixes.

Re-exports `heal_repo`, the library-mode entry point for the v1 client
contract (see `selfrepair.api.v1`). It is a thin wrapper around
`run_healing_loop` that adapts to the (full_name, issues, safe_only, branch)
signature expected by matrix-maintainer's LocalClient.
"""
from selfrepair.api.v1.engines import heal_repo

__all__ = ["heal_repo"]
