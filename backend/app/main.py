from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes import router

app = FastAPI(
    title="SelfRepair Repo",
    description=(
        "Production-ready API for repository health scanning, safe AI-assisted repair, "
        "validation, and audit-ready reporting. Defaults to dry-run safety."
    ),
    version="1.0.0",
)

app.include_router(router)
