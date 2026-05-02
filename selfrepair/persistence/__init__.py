"""Postgres-backed state for jobs, findings, repairs, audit, provenance.

Per ADR-0003. The git tree is the source of truth for repairs; this database
holds the operational state that lets the worker reason about runs,
deduplicate findings, and answer "have we already opened a PR for this finding
on this commit SHA?" lookups.
"""
from selfrepair.persistence.db import Base, get_engine, get_sessionmaker

__all__ = ["Base", "get_engine", "get_sessionmaker"]
