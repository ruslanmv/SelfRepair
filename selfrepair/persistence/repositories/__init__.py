"""Data access objects — the only code that touches ORM models directly.

Higher layers (worker, API) use these repositories so SQL is contained and
intent-revealing methods can be unit-tested with a single fake session.
"""
from selfrepair.persistence.repositories.ci import CIRepository
from selfrepair.persistence.repositories.findings import FindingsRepository
from selfrepair.persistence.repositories.issues import IssuesRepository
from selfrepair.persistence.repositories.jobs import JobsRepository
from selfrepair.persistence.repositories.repairs import RepairsRepository
from selfrepair.persistence.repositories.repos import ReposRepository

__all__ = [
    "CIRepository",
    "FindingsRepository",
    "IssuesRepository",
    "JobsRepository",
    "RepairsRepository",
    "ReposRepository",
]
