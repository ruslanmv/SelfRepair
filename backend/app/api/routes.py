from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.orchestrator.repo_orchestrator import RepoOrchestrator
from backend.app.schemas.repo_request import RepoRequest

router = APIRouter()
orchestrator = RepoOrchestrator()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "selfrepair-repo-api"}


@router.post("/repo/inference")
async def repo_inference(request: RepoRequest) -> dict:
    return _run_orchestrator(request)


@router.post("/scan-repo")
async def scan_repo(request: RepoRequest) -> dict:
    result = _run_orchestrator(request)
    return {
        "repo": result["repo"],
        "repo_url": result["repo_url"],
        "branch": result["branch"],
        "health_score_before": result["health_score_before"],
        "issues_found": result["issues_found"],
        "issues": result["issues"],
        "validation_status": result["validation_status"],
    }


@router.post("/repair")
async def repair(request: RepoRequest) -> dict:
    result = _run_orchestrator(request)
    return {
        "repo": result["repo"],
        "repair_mode": result["repair_mode"],
        "fixes_applied": result["fixes_applied"],
        "changed_files": result["changed_files"],
        "repair_patches": result["repair_patches"],
        "notes": result["notes"],
    }


@router.post("/validate")
async def validate(request: RepoRequest) -> dict:
    result = _run_orchestrator(request)
    return {
        "repo": result["repo"],
        "validation_status": result["validation_status"],
        "validation": result["validation"],
        "health_score_after": result["health_score_after"],
    }


@router.get("/report/{repo_id}")
async def report(repo_id: str) -> dict:
    return {
        "repo_id": repo_id,
        "message": "Reports are generated on demand. Call POST /repo/inference with repo_url to create a fresh report.",
    }


@router.post("/v1/rpc")
async def rpc(payload: dict) -> dict:
    method = payload.get("method", "repo.selfrepair")
    if method not in {"repo.selfrepair", "selfrepair.run", "repo.scan"}:
        raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")
    params = payload.get("params", {})
    try:
        request = RepoRequest(
            repo_url=params.get("repo_url", ""),
            branch=params.get("branch", "main"),
            repair_mode=params.get("repair_mode", "dry_run"),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _run_orchestrator(request)
    return {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {
            "summary": f"SelfRepair completed for {result['repo']} with status {result['validation_status']}",
            "health_score": f"{result['health_score_before']} → {result['health_score_after']}",
            "validation": result["validation_status"],
            "repo": result["repo"],
            "report": result,
        },
    }


def _run_orchestrator(request: RepoRequest) -> dict:
    try:
        return orchestrator.run(str(request.repo_url), request.branch, request.repair_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
