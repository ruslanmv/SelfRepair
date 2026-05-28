# v1 RPC Contract — SelfRepair Side

This is the SelfRepair-side implementation of the contract defined in
[`agent-matrix/matrix-maintainer:docs/design/selfrepair-client-contract.md`](https://github.com/agent-matrix/matrix-maintainer/blob/main/docs/design/selfrepair-client-contract.md).

Two surfaces, one contract:

1. **HTTP**: JSON-RPC 2.0 at `POST /v1/rpc`, plus `GET /v1/about`.
2. **Library** (in-process): top-level functions importable from this package.

Both speak the same DTOs (`selfrepair.api.v1.dtos`), and every DTO carries
`schema_version = "selfrepair/v1"`.

## HTTP surface

### `GET /v1/about`

```json
{
  "schema_versions": ["selfrepair/v1"],
  "service": "selfrepair",
  "version": "2.0.0"
}
```

### `POST /v1/rpc`

JSON-RPC 2.0. Four methods:

| Method                 | Params                                                          | Result                  |
|------------------------|-----------------------------------------------------------------|-------------------------|
| `selfrepair.scan`      | `repo: str, profile?: str`                                      | `RepoHealthReportDTO`   |
| `selfrepair.repair`    | `repo: str, issues: list, safe_only: bool, branch?: str`        | `RepairResultDTO`       |
| `selfrepair.validate`  | `repo: str, in_sandbox: bool`                                   | `ValidationReportDTO`   |
| `selfrepair.report`    | `repo: str`                                                     | `JsonReportDTO`         |

All four also accept optional `platform` (`"github" | "gitlab" | "huggingface"`,
default `"github"`) and `clone_url` (string) to override platform-derived
defaults when calling against private mirrors or non-canonical hosts.

### Error envelope

Standard JSON-RPC 2.0 error codes:

| Code     | Meaning                                                     |
|----------|-------------------------------------------------------------|
| `-32700` | parse error (bad JSON body)                                 |
| `-32600` | invalid request (missing/wrong `jsonrpc`, bad shape, auth)  |
| `-32601` | method not found                                            |
| `-32602` | invalid params (validation failure)                         |
| `-32603` | internal error (engine raised; structured, never a 500)     |

A 500 only escapes when FastAPI itself crashes — engine exceptions are
caught and turned into `-32603`.

### Auth

`Authorization: Bearer <token>`, compared against the `SELFREPAIR_API_KEY`
env var. If the env is unset, the endpoint runs in **local-dev mode** —
unauthenticated requests are accepted and a warning is logged at boot.

### CORS

`/v1/*` allows `*` origins, no credentials, so the matrix-maintainer status
site can call it directly when proxied.

## Library surface

The same engines are exposed in-process for `matrix-maintainer`'s
`LocalClient`:

```python
from selfrepair.scanners  import scan_repo       # -> RepoHealthReportDTO
from selfrepair.healing   import heal_repo       # -> RepairResultDTO
from selfrepair.matrixlab import validate_repo   # -> ValidationReportDTO
```

These are thin adapters around `analyzers.repo_analyzer`,
`healing.healing_loop`, and `matrixlab.verifier`. They share the same DTOs
as the HTTP surface, so a caller can swap between transports without
re-typing the result.

## Mapping to existing engines

| Contract method        | Wired to                                                                  |
|------------------------|---------------------------------------------------------------------------|
| `selfrepair.scan`      | `SandboxManager.clone_repo` + `analyze_repo_layout` + `verify_repo`        |
| `selfrepair.repair`    | `SandboxManager.clone_repo` + `analyze_repo_layout` + `run_healing_loop`   |
| `selfrepair.validate`  | `SandboxManager.clone_repo` + `verifier.verify_repo`                       |
| `selfrepair.report`    | composes `scan_repo` + `validate_repo` (no repair side-effect)             |

### Adapter notes

- **`heal_repo(issues=...)`** — the v1 `issues` list is currently advisory;
  the engine re-derives its own plan from the working tree. The request is
  echoed back in `metadata.requested_issues` so the caller can audit what
  it asked for.
- **`status` mapping** — internal `"repaired"` collapses to v1 `"healthy"`
  (the v1 enum is `healthy | degraded | down | unknown`).
- **`sandbox`** — `in_sandbox=True` labels the report `"matrixlab"`. The
  verifier currently runs locally inside the worker; the field is the
  stable contract, not a deployment claim.

## Stability

Bumping `schema_version` away from `selfrepair/v1` is a breaking change and
must be coordinated with matrix-maintainer's
`docs/design/selfrepair-client-contract.md`.
