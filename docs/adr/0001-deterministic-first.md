# ADR-0001: Deterministic-first, AI-second

## Status
Accepted — 2026-05-01

## Context
Auto-repair tools that lead with LLMs build a reputation for breaking working code
faster than they fix broken code. Tools that lead with deterministic rules
(Renovate, Dependabot) ship millions of PRs daily and have become trusted defaults.
The blast radius of an unattended fleet tool is large; trust is the moat.

## Decision
Every finding is matched against the `Fixer` rule registry first. The LLM tier
(GitPilot → OllaBridge) is invoked only when:

1. No deterministic `Fixer` matches the finding kind, AND
2. The repository has explicitly opted into LLM repair for that kind in
   `.selfrepair.yml` under `escalate_to_llm:`.

Default for a repo without a `.selfrepair.yml` is **rule-based fixers only, dry-run
branch, no auto-merge**.

## Consequences
- Most repairs never call an LLM. Faster, cheaper, auditable.
- The plugin SDK (ADR-0004) becomes the long-term product surface, not the agent loop.
- LLM cost is a knob the customer controls, not a fixed product feature.
- Slightly more upfront work than "throw the diff at a frontier model."

## Rejected alternatives
- **LLM-first with rule fallback.** Cost, latency, and trust profile all worse.
- **Rules-only.** Caps the addressable problem at the templated long tail.
