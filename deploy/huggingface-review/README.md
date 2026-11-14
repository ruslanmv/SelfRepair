---
title: SelfRepair Review
emoji: 💡
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: AI pull-request reviewer for GitHub (development edition)
---

# SelfRepair Review — development Space

An AI reviewer for GitHub pull requests. When a pull request is opened or marked
ready for review, it:

1. adds 👀 to the pull request and posts a **SelfRepair Review Summary** comment
   (status, reviewed commit, what triggered the review), edited in place on every run;
2. sets the **SelfRepair / Review** check on the head commit;
3. posts a **💡 SelfRepair Review** with inline suggestions, each led by a
   P0–P3 priority badge and ending with "Useful? React with 👍 / 👎.";
   a clean commit gets "Didn't find any major issues. 🚀".

On a pull request, maintainers can comment:

| Comment | What happens |
| --- | --- |
| `@selfrepair review` | Review the latest commit again. 👀 on your comment. |
| `@selfrepair fix` | Ask GitPilot for a **draft** pull request that addresses the open suggestions. |

`@gitpilot` works as an alias. Only commenters who are an owner, member or
collaborator of the repository are obeyed. SelfRepair never approves or merges.

This edition runs in one process with an in-memory store: review history resets
when the Space restarts. Production uses the full SelfRepair server
(PostgreSQL, Redis, Arq worker) — see `docs/reviewer/deployment.md`.

## Set up (once)

1. **Space secrets** (Settings → Variables and secrets):
   - `SELFREPAIR_SETUP_TOKEN` — any long random string; it unlocks `/setup`.
   - `HF_TOKEN` — a token with write access to this Space, used only to save the
     GitHub App credentials as Space secrets.
   - `SELFREPAIR_ALLOWED_OWNERS` (variable) — e.g. `ruslanmv`. Repositories of
     other owners are ignored even if the app is installed there.
2. Open `https://<space-host>/setup?token=<SELFREPAIR_SETUP_TOKEN>` and press
   **Create GitHub App on GitHub**. GitHub creates a private app whose webhook
   points at this Space; the app id, private key and webhook secret are saved
   as Space secrets and never shown.
3. Install the app on the repositories to review.
4. **Model** — set these to turn on the model review (otherwise only the
   deterministic checks run and the check says the model review is missing):
   - `SELFREPAIR_REVIEW_LLM_URL` — an OpenAI-compatible base URL, e.g.
     `https://ruslanmv-ollabridge.hf.space/v1` (OllaBridge Cloud).
   - `SELFREPAIR_REVIEW_MODEL` — the model id.
   - `SELFREPAIR_REVIEW_LLM_KEY` (secret) — the endpoint's key.
   - `SELFREPAIR_REVIEW_FALLBACK_MODEL` (optional) — a model used only for parts
     the main model could not answer, e.g. `grok-best` behind `free-best`.
   - `SELFREPAIR_REVIEW_MAX_SECONDS` (optional, default 1200) — time budget for
     one review.
5. **Fixes** (optional): `SELFREPAIR_REMEDIATION=true`, `GITPILOT_URL`, and the
   secret `GITPILOT_TOKEN`.

`/healthz` reports what is configured (booleans only).
