# Safety Model

SelfRepair Repo is designed to be safe by default.

## Modes

| Mode | Behavior |
| --- | --- |
| `dry_run` | Clone, analyze, suggest repairs, and report. No push. |
| `suggest` | Same as dry-run, with Bob-ready repair prompts. |
| `apply_local` | Apply local safe template fixes in the sandbox only. |
| `branch` | Prepare a repair branch when write access is enabled. |
| `pull_request` | Create a PR/MR only when explicitly configured. |

## Guardrails

- No direct push by default.
- Repair changes are limited by `MAX_AUTOFIX_FILES`.
- Patch paths must remain inside the sandbox workspace.
- Command execution is timeout-bounded.
- Reports include changed files, notes, validation status, and policy risk.

## Recommended production setup

- Run as a non-root container user.
- Mount a disposable work directory.
- Use read-only repository tokens for scanning.
- Use write tokens only in a separate reviewed PR workflow.
