// Mock data for SelfRepair Console.
// All data is realistic and internally consistent.
//
// To wire to the real API, replace each constant with a query against the
// FastAPI endpoints (e.g. /api/v1/repos, /api/v1/findings, etc.). Keeping
// the shape stable means surfaces don't need to change.

const repos = [
  { id: "R-1042", name: "agent-matrix/matrix-hub", platform: "github", lang: "Python", health: 86, openFindings: 4, repairs: 12, lastJob: "2m ago", branch: "main", visibility: "public", owner: "agent-matrix", stars: 482 },
  { id: "R-1043", name: "ruslanmv/gitpilot", platform: "github", lang: "TypeScript", health: 72, openFindings: 9, repairs: 31, lastJob: "8m ago", branch: "main", visibility: "public", owner: "ruslanmv", stars: 154 },
  { id: "R-1044", name: "agent-matrix/matrix-llm", platform: "github", lang: "Python", health: 94, openFindings: 1, repairs: 4, lastJob: "1m ago", branch: "main", visibility: "public", owner: "agent-matrix", stars: 87 },
  { id: "R-1045", name: "ruslanmv/SelfRepair", platform: "github", lang: "Python", health: 78, openFindings: 6, repairs: 18, lastJob: "12m ago", branch: "master", visibility: "private", owner: "ruslanmv", stars: 0 },
  { id: "R-1046", name: "ruslanmv/HomePilot", platform: "github", lang: "Python", health: 64, openFindings: 13, repairs: 7, lastJob: "5m ago", branch: "master", visibility: "public", owner: "ruslanmv", stars: 268 },
  { id: "R-1047", name: "agent-matrix/matrix-cli", platform: "github", lang: "Python", health: 91, openFindings: 2, repairs: 9, lastJob: "23m ago", branch: "master", visibility: "public", owner: "agent-matrix", stars: 41 },
  { id: "R-1048", name: "platform/payments-svc", platform: "gitlab", lang: "Go", health: 41, openFindings: 22, repairs: 3, lastJob: "44s ago", branch: "main", visibility: "private", owner: "platform", stars: 0 },
  { id: "R-1049", name: "platform/billing-api", platform: "gitlab", lang: "Go", health: 58, openFindings: 14, repairs: 8, lastJob: "3m ago", branch: "main", visibility: "private", owner: "platform", stars: 0 },
  { id: "R-1050", name: "platform/audit-ledger", platform: "gitlab", lang: "Rust", health: 88, openFindings: 3, repairs: 11, lastJob: "11m ago", branch: "main", visibility: "private", owner: "platform", stars: 0 },
  { id: "R-1051", name: "ruslanmv/ollabridge", platform: "github", lang: "Python", health: 82, openFindings: 5, repairs: 14, lastJob: "32m ago", branch: "master", visibility: "public", owner: "ruslanmv", stars: 211 },
  { id: "R-1052", name: "agent-matrix/matrixlab", platform: "github", lang: "Python", health: 76, openFindings: 7, repairs: 21, lastJob: "1h ago", branch: "master", visibility: "public", owner: "agent-matrix", stars: 56 },
  { id: "R-1053", name: "ruslanmv/clouddeploy", platform: "github", lang: "TypeScript", health: 69, openFindings: 11, repairs: 6, lastJob: "2h ago", branch: "master", visibility: "public", owner: "ruslanmv", stars: 78 },
  { id: "R-1054", name: "huggingface/granite-medical", platform: "huggingface", lang: "Python", health: 53, openFindings: 17, repairs: 2, lastJob: "4m ago", branch: "main", visibility: "public", owner: "huggingface", stars: 0 },
  { id: "R-1055", name: "agent-matrix/catalog", platform: "github", lang: "JSON", health: 96, openFindings: 0, repairs: 5, lastJob: "18m ago", branch: "main", visibility: "public", owner: "agent-matrix", stars: 23 },
  { id: "R-1056", name: "ruslanmv/jobcraft", platform: "github", lang: "Python", health: 71, openFindings: 8, repairs: 4, lastJob: "55m ago", branch: "master", visibility: "public", owner: "ruslanmv", stars: 92 },
  { id: "R-1057", name: "platform/notifications", platform: "gitlab", lang: "Node", health: 80, openFindings: 5, repairs: 13, lastJob: "9m ago", branch: "main", visibility: "private", owner: "platform", stars: 0 },
  { id: "R-1058", name: "ruslanmv/Nexus", platform: "github", lang: "Rust", health: 89, openFindings: 2, repairs: 7, lastJob: "27m ago", branch: "master", visibility: "public", owner: "ruslanmv", stars: 134 },
];

const findings = [
  { fp: "F-9001", kind: "missing-pyproject", severity: "high", repo: "ruslanmv/SelfRepair", path: "pyproject.toml", count: 1, firstSeen: "Apr 28", state: "open", suggested: "auto-fix:pyproject" },
  { fp: "F-9002", kind: "stale-dep:requests<2.31", severity: "critical", repo: "platform/payments-svc", path: "go.sum", count: 4, firstSeen: "Apr 30", state: "open", suggested: "llm-assist" },
  { fp: "F-9003", kind: "no-makefile-test", severity: "medium", repo: "ruslanmv/HomePilot", path: "Makefile", count: 1, firstSeen: "May 01", state: "open", suggested: "auto-fix:makefile" },
  { fp: "F-9004", kind: "secret-leak:gh_pat", severity: "critical", repo: "ruslanmv/HomePilot", path: ".env.example", count: 1, firstSeen: "May 02", state: "open", suggested: "manual-review" },
  { fp: "F-9005", kind: "python-pin<3.11", severity: "high", repo: "platform/billing-api", path: "pyproject.toml", count: 2, firstSeen: "Apr 29", state: "in-repair", suggested: "auto-fix:python311" },
  { fp: "F-9006", kind: "missing-health-test", severity: "low", repo: "ruslanmv/gitpilot", path: "tests/", count: 1, firstSeen: "May 02", state: "open", suggested: "auto-fix:health_test" },
  { fp: "F-9007", kind: "license-missing", severity: "medium", repo: "huggingface/granite-medical", path: "LICENSE", count: 1, firstSeen: "Apr 27", state: "open", suggested: "auto-fix:readme" },
  { fp: "F-9008", kind: "deprecated-api:request_get", severity: "medium", repo: "ruslanmv/clouddeploy", path: "src/cloud/fetch.ts", count: 6, firstSeen: "Apr 30", state: "suppressed", suggested: "manual-review" },
];

const repairs = [
  { id: "PR-2210", repo: "ruslanmv/SelfRepair", title: "Add pyproject.toml with Python 3.11 baseline", state: "awaiting-approval", cost: 0.024, signed: true, policy: "auto-fix:pyproject", findings: 1, opened: "4m ago", branch: "selfrepair/auto/pyproject-init", lines: { added: 38, removed: 0 } },
  { id: "PR-2209", repo: "platform/billing-api", title: "Pin python>=3.11 and bump uv lockfile", state: "merged", cost: 0.011, signed: true, policy: "auto-fix:python311", findings: 2, opened: "1h ago", branch: "selfrepair/auto/py311", lines: { added: 12, removed: 4 } },
  { id: "PR-2208", repo: "ruslanmv/HomePilot", title: "Generate health probe + Makefile install/test", state: "awaiting-approval", cost: 0.018, signed: true, policy: "auto-fix:health_test", findings: 1, opened: "12m ago", branch: "selfrepair/auto/health-probe", lines: { added: 64, removed: 2 } },
  { id: "PR-2207", repo: "ruslanmv/gitpilot", title: "LLM-assisted: replace deprecated http.Client init", state: "in-sandbox", cost: 0.052, signed: false, policy: "llm-assist", findings: 3, opened: "22m ago", branch: "selfrepair/llm/http-client-fix", lines: { added: 21, removed: 18 } },
  { id: "PR-2206", repo: "platform/audit-ledger", title: "Add SBOM generation to release workflow", state: "merged", cost: 0.009, signed: true, policy: "auto-fix:readme", findings: 1, opened: "3h ago", branch: "selfrepair/auto/sbom", lines: { added: 28, removed: 0 } },
  { id: "PR-2205", repo: "ruslanmv/HomePilot", title: "Rotate GH PAT placeholder (manual review)", state: "blocked-policy", cost: 0.002, signed: false, policy: "deny:secrets", findings: 1, opened: "8m ago", branch: "selfrepair/manual/secret-rotate", lines: { added: 1, removed: 1 } },
  { id: "PR-2204", repo: "agent-matrix/matrix-hub", title: "Update README front-matter for HF compatibility", state: "merged", cost: 0.005, signed: true, policy: "auto-fix:readme", findings: 1, opened: "5h ago", branch: "selfrepair/auto/readme-fm", lines: { added: 9, removed: 6 } },
];

const jobs = [
  { id: "J-77821", repo: "ruslanmv/SelfRepair", trigger: "webhook:push", state: "running", started: "00:00:42", duration: "00:01:18", stage: "heal", events: 47 },
  { id: "J-77820", repo: "platform/payments-svc", trigger: "schedule:daily", state: "running", started: "00:01:13", duration: "00:00:48", stage: "analyze", events: 22 },
  { id: "J-77819", repo: "ruslanmv/HomePilot", trigger: "manual:ruslanmv", state: "succeeded", started: "12m ago", duration: "00:02:04", stage: "report", events: 88 },
  { id: "J-77818", repo: "platform/billing-api", trigger: "webhook:pr", state: "succeeded", started: "1h ago", duration: "00:01:51", stage: "report", events: 71 },
  { id: "J-77817", repo: "ruslanmv/gitpilot", trigger: "webhook:push", state: "failed", started: "22m ago", duration: "00:00:34", stage: "validate", events: 18 },
  { id: "J-77816", repo: "agent-matrix/matrix-hub", trigger: "schedule:daily", state: "succeeded", started: "2h ago", duration: "00:01:22", stage: "report", events: 54 },
  { id: "J-77815", repo: "huggingface/granite-medical", trigger: "manual:ruslanmv", state: "queued", started: "—", duration: "—", stage: "queued", events: 0 },
];

// Sparkline series generator (24 points each, 8-96)
export const spark = (seed) => {
  const out = [];
  let v = 50 + (seed % 20);
  for (let i = 0; i < 24; i++) {
    v += Math.sin(seed + i * 0.7) * 8 + (i % 3 === 0 ? 6 : -3);
    v = Math.max(8, Math.min(96, v));
    out.push(v);
  }
  return out;
};

const dashboard = {
  kpis: [
    { label: "Repos under management", value: "1,284", delta: "+12 this week", series: spark(3), tone: "info" },
    { label: "Open findings", value: "342", delta: "−24 vs. yesterday", series: spark(7), tone: "warn" },
    { label: "Repairs merged (7d)", value: "168", delta: "+18%", series: spark(11), tone: "ok" },
    { label: "Mean time to repair", value: "4m 22s", delta: "−38s", series: spark(15), tone: "ok" },
  ],
  fleetHealth: [
    { band: "90–100", count: 612, tone: "ok" },
    { band: "70–89",  count: 408, tone: "info" },
    { band: "50–69",  count: 174, tone: "warn" },
    { band: "<50",    count: 90,  tone: "danger" },
  ],
  repairCost: { spend: "$48.21", budget: "$200.00", monthLabel: "May 2026" },
  activity: [
    { t: "00:00:14", text: "Repair PR-2210 awaiting approval", repo: "ruslanmv/SelfRepair", tone: "info" },
    { t: "00:00:42", text: "Sigstore signature verified", repo: "platform/audit-ledger", tone: "ok" },
    { t: "00:01:08", text: "Sandbox validation succeeded", repo: "platform/billing-api", tone: "ok" },
    { t: "00:02:55", text: "Policy denied repair — secret detected", repo: "ruslanmv/HomePilot", tone: "danger" },
    { t: "00:04:11", text: "LLM repair generated", repo: "ruslanmv/gitpilot", tone: "info" },
    { t: "00:05:33", text: "Daily fleet scan started", repo: "1,284 repos", tone: "muted" },
  ],
};

// Issue Watch: human-created issues from external repository platforms
// (GitHub Issues, GitLab Issues, Hugging Face Community Discussions). Distinct
// from `findings` (internal scanner output) and from `repairs` (internal jobs).
// `repairClass` mirrors the deterministic classification the backend emits:
// documentation/dependency/runtime/configuration → repairable, security/bug/
// feature/unknown → human triage. Priority is provider-mapped from labels.
const externalIssues = [
  {
    id: "I-GH-1042",
    provider: "github",
    repo: "ruslanmv/SelfRepair",
    number: 12,
    title: "CI fails when pyproject dependencies are missing",
    state: "open",
    labels: ["bug", "ci", "good-first-issue"],
    author: "human-user",
    priority: "high",
    repairClass: "ci_failure",
    repairable: true,
    updated: "8m ago",
    externalUrl: "https://github.com/ruslanmv/SelfRepair/issues/12",
    repairJobId: null,
    bodyExcerpt: "uv sync exits 1 when [tool.uv] section is absent. Repro on fresh clone…",
  },
  {
    id: "I-GL-901",
    provider: "gitlab",
    repo: "platform/audit-ledger",
    number: 901,
    title: "Release workflow missing SBOM artifact",
    state: "opened",
    labels: ["release", "compliance"],
    author: "devops",
    priority: "medium",
    repairClass: "configuration",
    repairable: true,
    updated: "1h ago",
    externalUrl: "https://gitlab.com/platform/audit-ledger/-/issues/901",
    repairJobId: "J-77820",
    bodyExcerpt: "Release tag pushes don't attach the syft-generated SBOM…",
  },
  {
    id: "I-HF-77",
    provider: "huggingface",
    repo: "huggingface/granite-medical",
    number: 77,
    title: "Space does not start after dependency update",
    state: "open",
    labels: ["space", "runtime"],
    author: "community-user",
    priority: "high",
    repairClass: "runtime",
    repairable: true,
    updated: "32m ago",
    externalUrl:
      "https://huggingface.co/spaces/huggingface/granite-medical/discussions/77",
    repairJobId: null,
    bodyExcerpt: "ImportError: cannot import name 'pipeline' from 'transformers'…",
  },
  {
    id: "I-GH-1881",
    provider: "github",
    repo: "ruslanmv/HomePilot",
    number: 1881,
    title: "Possible secret leakage in .env.example",
    state: "open",
    labels: ["security", "needs-triage"],
    author: "secops",
    priority: "critical",
    repairClass: "security",
    repairable: false,
    updated: "12m ago",
    externalUrl: "https://github.com/ruslanmv/HomePilot/issues/1881",
    repairJobId: null,
    bodyExcerpt:
      "Looks like a real GH PAT-shaped string committed in .env.example. Escalating…",
  },
  {
    id: "I-GH-2210",
    provider: "github",
    repo: "ruslanmv/gitpilot",
    number: 2210,
    title: "Outdated install instructions in README",
    state: "open",
    labels: ["documentation", "good-first-issue"],
    author: "newcomer",
    priority: "low",
    repairClass: "documentation",
    repairable: true,
    updated: "3h ago",
    externalUrl: "https://github.com/ruslanmv/gitpilot/issues/2210",
    repairJobId: null,
    bodyExcerpt: "README still references `pip install gitpilot` but PyPI name is…",
  },
  {
    id: "I-GL-455",
    provider: "gitlab",
    repo: "platform/payments-svc",
    number: 455,
    title: "Bump go-jose to 4.0.4 (CVE-2024-28180)",
    state: "opened",
    labels: ["dependency", "security-patch"],
    author: "renovate",
    priority: "high",
    repairClass: "dependency",
    repairable: true,
    updated: "47m ago",
    externalUrl: "https://gitlab.com/platform/payments-svc/-/issues/455",
    repairJobId: null,
    bodyExcerpt: "Vulnerable go-jose version in go.sum. Fix is a single bump…",
  },
  {
    id: "I-GH-44",
    provider: "github",
    repo: "agent-matrix/matrix-cli",
    number: 44,
    title: "Add JSON output mode for `matrix list`",
    state: "open",
    labels: ["feature-request"],
    author: "power-user",
    priority: "low",
    repairClass: "feature_request",
    repairable: false,
    updated: "1d ago",
    externalUrl: "https://github.com/agent-matrix/matrix-cli/issues/44",
    repairJobId: null,
    bodyExcerpt: "Would love `--output json` so I can pipe to jq…",
  },
];

const issueKpis = {
  open: 7,
  highPriority: 3,
  repairable: 5,
  repairsStarted: 1,
};

const liveEvents = [
  { t: "+00:00.00", lvl: "info",  msg: "Job J-77821 created from webhook push@a8f12c4" },
  { t: "+00:00.04", lvl: "info",  msg: "Resolving repository ruslanmv/SelfRepair" },
  { t: "+00:00.18", lvl: "info",  msg: "Cloned in 142ms · branch=master · sha=a8f12c4" },
  { t: "+00:00.31", lvl: "info",  msg: "Stage:analyze starting · 7 analyzers loaded" },
  { t: "+00:00.42", lvl: "ok",    msg: "Layout detected: python-uv · pyproject.toml present" },
  { t: "+00:00.58", lvl: "warn",  msg: "Finding F-9001: missing-pyproject:tool.uv section" },
  { t: "+00:01.04", lvl: "info",  msg: "Stage:heal starting · candidate strategies=3" },
  { t: "+00:01.12", lvl: "info",  msg: "Strategy auto-fix:pyproject selected (confidence 0.94)" },
  { t: "+00:01.21", lvl: "info",  msg: "Sandbox container matrixlab-py311 spun up (642ms)" },
  { t: "+00:01.39", lvl: "ok",    msg: "Patch generated · +38/-0 lines" },
  { t: "+00:01.46", lvl: "info",  msg: "Stage:validate starting" },
  { t: "+00:01.54", lvl: "ok",    msg: "uv sync · 0 errors · 4.2s" },
  { t: "+00:01.62", lvl: "ok",    msg: "pytest tests/test_health.py · 1 passed" },
  { t: "+00:01.78", lvl: "info",  msg: "Policy decision: ALLOW · auto-fix:pyproject" },
  { t: "+00:01.86", lvl: "ok",    msg: "Sigstore bundle attached · cosign verified" },
  { t: "+00:01.94", lvl: "info",  msg: "Stage:report · drafting PR" },
  { t: "+00:02.08", lvl: "ok",    msg: "PR-2210 opened · awaiting human approval" },
];

export const SR_DATA = {
  repos,
  findings,
  repairs,
  jobs,
  dashboard,
  liveEvents,
  externalIssues,
  issueKpis,
  spark,
};
