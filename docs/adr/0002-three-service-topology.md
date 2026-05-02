# ADR-0002: Three-service topology — SelfRepair / GitPilot / OllaBridge

## Status
Accepted — 2026-05-01

## Context
SelfRepair, GitPilot, and OllaBridge currently exist as related-but-separate
codebases. The temptation is to merge them or have one import another. This ADR
fixes the boundary so each service can evolve independently and the LLM blast
radius stays contained.

## Decision
Three services, three responsibilities:

- **SelfRepair** owns the repository: discovery, sandbox, policy, git, PR.
- **GitPilot** owns the agent loop: Explorer → Planner → Coder → Reviewer.
- **OllaBridge** owns the model gateway: routing, caching, budgets, observability.

SelfRepair calls GitPilot over HTTP/SSE (see `selfrepair/connectors/gitpilot.py`).
Both services target OllaBridge as their only LLM endpoint.

GitPilot **never** holds a git credential. SelfRepair sends a git bundle and
receives a patch; SelfRepair owns the push and the PR.

## Consequences
- Each service scales independently.
- Swapping any one service is contained behind a contract.
- One extra network hop on the LLM path; mitigated by OllaBridge's prompt cache.
- Operations teams must run three services; mitigated by a single Helm chart.

## Rejected alternatives
- **Vendor GitPilot as a Python library inside SelfRepair.** Couples release
  cycles, doubles the test surface, and removes the credential isolation that
  makes the design defensible to a security review.
- **Inline OllaBridge into SelfRepair.** Loses the per-tenant prompt cache and
  cost gate that benefits both consumers.
