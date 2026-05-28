"""SelfRepair v1 stable client contract.

This subpackage is the SelfRepair-side implementation of the contract defined
in `agent-matrix/matrix-maintainer:docs/design/selfrepair-client-contract.md`.

Surface:
  * DTOs:       `selfrepair.api.v1.dtos`
  * HTTP:       `selfrepair.api.v1.rpc.router` (mounted by `api.main`)
  * Library:    `selfrepair.api.v1.engines.{scan_repo,heal_repo,validate_repo}`

The library-mode functions are also re-exported at the top-level package
locations expected by matrix-maintainer's LocalClient:
  * `selfrepair.scanners.scan_repo`
  * `selfrepair.healing.heal_repo`
  * `selfrepair.matrixlab.validate_repo`
"""
from selfrepair.api.v1 import dtos, engines, rpc

__all__ = ["dtos", "engines", "rpc"]
