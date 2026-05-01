# Security Policy

SelfRepair Repo can clone and modify repositories, so safety is a product requirement.

## Supported versions

Security fixes are applied to the latest released minor version and the `main` branch.

## Safe defaults

- `DRY_RUN=true` by default.
- `ALLOW_AUTOFIX_PR=false` by default.
- `ALLOW_DIRECT_PUSH=false` by default.
- API repair mode defaults to `dry_run`.
- The service never needs a write token for scan-only usage.
- Generated patches should be reviewed before they are committed or pushed.

## Reporting a vulnerability

Open a private security advisory in GitHub or contact the maintainers directly. Please include:

- affected version or commit
- reproduction steps
- impact
- suggested remediation, if available

## Operational guidance

Do not run SelfRepair Repo with broad write tokens in shared environments. Prefer short-lived tokens, least privilege, isolated workspaces, and ephemeral containers.
