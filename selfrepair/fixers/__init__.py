"""Reference fixers shipped in core.

Per ADR-0004 the SDK is the long-term product surface; these are the
reference implementations that demonstrate the `Fixer` protocol. Community
fixers are discovered later via Python entry points and override these by id.
"""
from selfrepair.fixers.health_test import HealthTestFixer
from selfrepair.fixers.makefile import MakefileFixer
from selfrepair.fixers.pyproject import PyProjectFixer
from selfrepair.sdk import FixerRegistry


def default_registry() -> FixerRegistry:
    """Build a registry pre-populated with all reference fixers."""
    registry = FixerRegistry()
    registry.register(MakefileFixer())
    registry.register(PyProjectFixer())
    registry.register(HealthTestFixer())
    return registry


__all__ = [
    "HealthTestFixer",
    "MakefileFixer",
    "PyProjectFixer",
    "default_registry",
]
