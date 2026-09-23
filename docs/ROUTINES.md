# SelfRepair Routines

Routines model repeatable repository-maintenance workflows without giving an AI
an implicit path to merge protected branches.

## Intended chain

A typical `develop -> master` lifecycle is represented as four independent,
composable routines:

1. **Health + AutoRepair** — inspect a configured branch daily and create a
   repair proposal/PR back into that branch.
2. **Merge Request Review** — inspect open PR/MR commits and diffs targeting the
   branch, record actionable review findings, and pause on uncertainty.
3. **Review Remediation** — consume unresolved review findings, prepare minimal
   fixes on the PR head branch, validate again, and request another review.
4. **Promotion Gate** — when the source branch is healthy and all required
   checks/reviews are resolved, prepare promotion to `main`/`master`.

The routines can depend on one another, so operators can build a pipeline
without hard-coding a specific branch name. A repo can use `develop`,
`dev-v0.1.4`, release branches, or any other convention.

## Protected-branch lock

`main` and `master` are protected by an application-level merge lock in
addition to any provider branch protection.

- Creating or retargeting a routine to `main`/`master` always enables the
  lock.
- A generic routine edit cannot disable it.
- Unlocking requires the dedicated merge-lock endpoint and an exact typed
  confirmation such as `UNLOCK master`.
- Even when unlocked, the shared merge guard still requires green checks and
  zero unresolved review threads.
- In `human_review` mode a human approval is also required.
- Every lock/unlock is written to the audit log.

Provider executors must call
`selfrepair.governance.merge_guard.evaluate_merge_guard` immediately before a
merge. This keeps the boundary independent of GitHub/GitLab implementation
details.

## API

- `GET /v1/routines/capabilities`
- `GET /v1/routines`
- `POST /v1/routines`
- `GET /v1/routines/{id}`
- `PATCH /v1/routines/{id}`
- `DELETE /v1/routines/{id}`
- `POST /v1/routines/{id}/merge-lock`
- `POST /v1/routines/{id}/merge-guard`
- `GET /v1/routines/{id}/runs`

## Execution boundary in this change

This change intentionally ships the **definition, UI, persistence, audit, and
merge-governance contract first**. `/v1/routines/capabilities` reports
`execution: definition_only`. No background worker is silently enabled by
adding the tab.

The executor can then be added as a separate reviewed change that consumes
these definitions and reuses the existing SelfRepair job/repair pipeline:

```text
routine due
  -> health_repair        -> existing scan/plan/repair/validate/publish pipeline
  -> pr_review            -> provider diff + review agent
  -> review_remediation   -> coder + validation + updated PR
  -> promotion            -> merge guard -> human approval OR auto merge
```

This split is deliberate: the operator can configure and review the exact
automation policy before any recurring remote-write behavior is activated.
