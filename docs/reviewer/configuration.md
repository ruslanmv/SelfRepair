# Reviewer configuration

Reviews are off until a repository opts in. A repository with no `reviewer` key keeps `enabled: false` and `engine: deterministic`.

Precedence, lowest first:

1. Code defaults.
2. Organization row from `PUT /v1/review-settings`.
3. `.selfrepair.yml` `reviewer` section.
4. Per-repository row from `PUT /v1/repos/{repo_id}/review-settings`.

```yaml
reviewer:
  enabled: false
  triggers:
    push: true
    pull_request: true
    merge_request: true
  branches:
    include:
      - main
      - master
      - develop
    exclude: []
  engine: deterministic   # or deepagents
  agents:
    security: true
    correctness: true
    architecture: true
    testing: true
  review:
    inline_comments: true
    publish_summary: true
    block_on:
      - critical
      - high
  execution:
    read_only: true
    sandbox_enabled: true
    max_runtime_seconds: 600
    max_tokens: 80000
    max_usd: 1.0
  remediation:
    enabled: false
    provider: gitpilot
    require_human_approval: true
    auto_merge: false
  policy_version: "1"
```

`read_only` only accepts `true`. `auto_merge` only accepts `false`. `engine: deepagents` does not by itself call a model; the process also needs the `reviewer` extra and the environment variables in the deployment guide.

Pushes are filtered on the branch that moved. Pull requests and merge requests are filtered on the target branch. `selfrepair/*` branches and the `selfrepair` / `selfrepair[bot]` sender are ignored so a repair push does not review itself.

`policy_version` is part of the run identity. Changing it reviews the same SHAs again under the new policy.
