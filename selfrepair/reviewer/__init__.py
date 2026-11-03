"""SelfRepair Reviewer.

Monitors opted-in repositories, reviews pushes and pull/merge requests, and
keeps code generation in GitPilot. Review runs are not repair jobs.
"""

from selfrepair.reviewer.schemas import CHECK_NAME

__all__ = ["CHECK_NAME"]
