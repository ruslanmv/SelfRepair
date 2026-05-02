"""External service connectors.

Keeps the seams to other services in one place. Anything that crosses a
process boundary belongs here.
"""
from selfrepair.connectors.gitpilot import (
    Budget,
    GitPilotClient,
    GitPilotError,
    RepairRequest,
    RepairResult,
    Workspace,
)

__all__ = [
    "Budget",
    "GitPilotClient",
    "GitPilotError",
    "RepairRequest",
    "RepairResult",
    "Workspace",
]
