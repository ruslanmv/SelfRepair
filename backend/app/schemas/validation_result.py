from __future__ import annotations

from pydantic import BaseModel


class ValidationResult(BaseModel):
    validation_status: str
    install_passed: bool = False
    tests_passed: bool = False
    start_passed: bool = False
    health_test_passed: bool = False
    notes: list[str] = []
