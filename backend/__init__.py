"""Internal engine package.

This package was previously the public API and is now demoted to an
internal helper that wraps `RepoOrchestrator`. The product API is
`selfrepair.api.main:app`. `backend.app.main:app` is kept only so
legacy CLIs and tests that import it continue to work, but it is no
longer started by docker-compose.

See `docs/PLAN_REMOVE_PLACEHOLDERS.md` §1.1 for the consolidation plan.
"""
