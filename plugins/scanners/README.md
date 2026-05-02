# SelfRepair scanner plugins

Each subdirectory is a scanner plugin. The minimum requirements are:

- A `plugin.yaml` manifest matching `selfrepair.scanners.plugin.ScannerPlugin`.
- An OCI image referenced from the manifest. Either pull a vendored image
  directly, or build a thin wrapper here (see `semgrep/Dockerfile` for the
  pattern).

The runner mounts:

- The repository read-only at `/in`
- An empty writable directory at `/out`

The scanner is expected to write its findings to `/out/findings.sarif` in
SARIF v2.1.0. Anything else is parsed as zero findings (with a warning).

Network defaults to `none`. Plugins that need to reach the internet (e.g.
for vulnerability DB updates) should set `network: bridge` and document why
in their manifest comments. Operators are expected to gate egress with an
allow-list at the host or sidecar proxy level (design §7).

## Bundled plugins

| ID         | Tool      | Purpose                                  | Network |
|------------|-----------|------------------------------------------|---------|
| `semgrep`  | Semgrep   | Static analysis (SAST) for source code   | bridge  |
| `trivy`    | Trivy     | SCA, secrets, config in deps and IaC     | bridge  |
| `gitleaks` | Gitleaks  | Secret detection (already-committed)     | none    |

## Adding a scanner

```bash
mkdir -p plugins/scanners/myscanner
$EDITOR plugins/scanners/myscanner/plugin.yaml
```

The runner will pick it up automatically once the manifest validates. No
Python changes required.
