"""MatrixLab sandbox + verifier.

Re-exports `validate_repo`, the library-mode entry point for the v1 client
contract (see `selfrepair.api.v1`). It is a thin wrapper around
`matrixlab.verifier.verify_repo`.
"""
from selfrepair.api.v1.engines import validate_repo

__all__ = ["validate_repo"]
