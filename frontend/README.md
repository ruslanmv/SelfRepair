# SelfRepair Console

Enterprise React frontend for the SelfRepair AI Secure Delivery Copilot.
Ported from the Claude Design hi-fi prototype.

## Stack

- **Vite 5** + **React 18** + plain JSX (no TS yet, easy to convert later)
- **CSS variables** for design tokens (dark + light, accent + density tweaks)
- **No client-side router** — the prototype uses a flat route enum, kept for now
  for parity with the design. React Router can be swapped in later without
  changing surface code.
- **Inter** + **JetBrains Mono** from Google Fonts

## Run it

```bash
make frontend-install   # one time
make frontend-dev       # Vite on :3000, /api proxied to the FastAPI backend on :8000
```

Or from this directory:

```bash
npm install
npm run dev
```

## Build & ship

```bash
make frontend-build           # static bundle in frontend/dist
make frontend-docker          # nginx-served image, ~30 MB
```

The Dockerfile is multi-stage; nginx serves the SPA on `:8080` and proxies
`/api/*` to the FastAPI backend (configurable via the upstream block in
`nginx.conf`).

## Surfaces

| Path | Surface | Notes |
|---|---|---|
| `/` | Overview | KPIs, fleet health, repair spend, live activity, awaiting-approval |
| `repos` | Inventory | virtualised table, filters, server-paginated (mock) |
| `repo/:id` | Repo detail | checks, recent jobs, findings, `.selfrepair.yml` editor |
| `findings` | Fleet findings | grouped by fingerprint, triage |
| `repairs` | Repair PRs | state, cost, signature |
| `repair/:id` | Repair detail | diff + policy trace + sandbox + provenance + conversation |
| `jobs` | Job log | live + history |
| `job/:id` | Job detail | live event stream, Gantt-like stage timeline |

## Features (toggleable)

- **Command palette** — `⌘K` jumps to any page, repo, repair, or job.
- **Run repair** — animated wizard: select target → policy gate → discover →
  analyze → plan → sandbox → sign & attest → open PR.
- **Audit log drawer** — right-side slide-in scoped to a job/repair/repo.
  Tamper-evident, Sigstore-attested.
- **AI chat dock** — bottom-right slide-up, scoped to current page (Findings /
  Repairs / Jobs / Fleet). Hidden by default; toggle from topbar.
- **Auto-repair mode** — multi-select repos + policy + schedule.
- **Tweaks** — dark/light, accent, density, layout. Persisted in localStorage.

## Mock data

All surfaces drive off `src/data/mock.js`. Wiring to the real API is a 1:1
swap inside that file (replace each constant with a `useQuery` against
`/api/v1/...` endpoints).
