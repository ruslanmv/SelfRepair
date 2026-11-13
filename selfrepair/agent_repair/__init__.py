"""Agent repair: a narrowly scoped intake for AI-agent issues sent by LangReplay.

An AI-agent issue (a replayed production failure with approved acceptance criteria) is not a repository-health
finding, so it does not go through the scan pipeline. This package gives it its own small path, built on
SelfRepair's persistence, audit log, worker queue and GitPilot client:

    POST /v1/agent-repairs                 intake: evidence + repository + pinned base commit -> read-only plan
    GET  /v1/agent-repairs/{id}            state, plan, patch, static checks, coder identity
    GET  /v1/agent-repairs/{id}/events     the job's events, after a sequence number
    POST /v1/agent-repairs/{id}/approve    a person's approval and file scope -> the patch, then static checks
    POST /v1/agent-repairs/{id}/draft-pr   push the candidate branch, open a DRAFT pull request
    POST /v1/agent-repairs/{id}/cancel     stop the job; nothing already produced is deleted

Every request is authenticated as a service (bearer token + HMAC signature) and bound to one org. Nothing here
merges, deploys, or writes outside the approved files. Routes: selfrepair/api/routes/agent_repairs.py. Contract: docs/agent-repair.md.
"""
