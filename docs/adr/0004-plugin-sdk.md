# ADR-0004: Plugin SDK is the long-term product surface

## Status
Accepted — 2026-05-01

## Context
Renovate's dominance of the dependency-update space comes almost entirely from
its package-manager plugin model. A closed set of internal-only fixers caps the
addressable problem at whatever the core team can ship.

## Decision
- A public `selfrepair.sdk` package defines the `Fixer` and `Scanner` protocols.
- Core ships ~10 reference fixers covering the Python / JS / Go basics.
- The long tail (`tf-deprecated-resource`, `dockerfile-pin-digest`,
  `helm-deprecated-api`, …) is community-built and discovered via Python entry
  points.
- Scanners run as containers with a SARIF v2.1.0 output contract — no language
  constraint, replaceable without code changes in the worker.

## Consequences
- Public SDK API stability becomes a hard commitment (semver).
- Test infrastructure must run third-party plugins under sandbox.
- Every internal fixer/scanner uses the same SDK as external ones — dogfooding
  enforces quality.

## Rejected alternatives
- **Internal-only Fixer interface.** Caps growth at core-team velocity.
- **Scanners as Python imports only.** Excludes the best tools in the ecosystem
  (Trivy, Semgrep, TruffleHog) which are written in Go/Rust.
