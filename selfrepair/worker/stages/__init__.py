"""Stage handlers for the worker pipeline.

Each handler is registered by `selfrepair.worker.main.build_pipeline` and
advances one job through one transition of the state machine. Handlers
share a per-job filesystem workspace via `selfrepair.worker.stages.sandbox`
and pass non-persistent state via `StageContext.extra`.
"""
from selfrepair.worker.stages.analyze import analyze_stage
from selfrepair.worker.stages.clone import clone_stage
from selfrepair.worker.stages.plan import plan_stage
from selfrepair.worker.stages.publish import publish_stage
from selfrepair.worker.stages.repair import repair_stage
from selfrepair.worker.stages.sandbox import workspace_for
from selfrepair.worker.stages.scan import scan_stage
from selfrepair.worker.stages.validate import validate_stage

__all__ = [
    "analyze_stage",
    "clone_stage",
    "plan_stage",
    "publish_stage",
    "repair_stage",
    "scan_stage",
    "validate_stage",
    "workspace_for",
]
