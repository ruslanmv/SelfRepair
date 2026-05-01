"""HuggingFace Spaces hardware management.

Manages ZeroGPU slot allocation:
- List current ZeroGPU usage across a namespace
- Auto-downgrade paused Spaces to free slots
- Request hardware upgrades for Spaces that need GPU
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_ZEROGPU_SLOTS = 10


@dataclass
class ZeroGPUSlot:
    space_id: str
    current_hardware: str | None
    requested_hardware: str | None
    stage: str

    @property
    def is_paused(self) -> bool:
        return self.stage in ("PAUSED", "SLEEPING")

    @property
    def is_zerogpu(self) -> bool:
        return "zero" in (self.requested_hardware or "").lower()


@dataclass
class HardwareReport:
    namespace: str
    total_slots: int = MAX_ZEROGPU_SLOTS
    used_slots: int = 0
    zerogpu_spaces: list[ZeroGPUSlot] = field(default_factory=list)
    paused_zerogpu: list[ZeroGPUSlot] = field(default_factory=list)
    active_zerogpu: list[ZeroGPUSlot] = field(default_factory=list)
    freed_slots: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def available_slots(self) -> int:
        return max(0, self.total_slots - self.used_slots + len(self.freed_slots))


def list_zerogpu_spaces(hf_api: object, namespace: str) -> list[ZeroGPUSlot]:
    """List all Spaces using ZeroGPU (current or requested) in a namespace."""
    slots = []
    try:
        spaces = list(hf_api.list_spaces(author=namespace))  # type: ignore[attr-defined]
    except Exception as exc:
        logger.error("Failed to list spaces for %s: %s", namespace, exc)
        return slots

    for space in spaces:
        try:
            info = hf_api.space_info(space.id)  # type: ignore[attr-defined]
            if not info.runtime:
                continue
            raw_hw = info.runtime.raw.get("hardware", {})
            cur = raw_hw.get("current", "")
            req = raw_hw.get("requested", "")
            if "zero" in str(cur).lower() or "zero" in str(req).lower():
                slots.append(ZeroGPUSlot(
                    space_id=space.id,
                    current_hardware=cur or None,
                    requested_hardware=req or None,
                    stage=info.runtime.stage or "unknown",
                ))
        except Exception:
            continue
    return slots


def build_hardware_report(hf_api: object, namespace: str) -> HardwareReport:
    """Build a full hardware usage report for a namespace."""
    report = HardwareReport(namespace=namespace)
    report.zerogpu_spaces = list_zerogpu_spaces(hf_api, namespace)
    report.used_slots = len(report.zerogpu_spaces)

    for slot in report.zerogpu_spaces:
        if slot.is_paused:
            report.paused_zerogpu.append(slot)
        else:
            report.active_zerogpu.append(slot)

    return report


def free_zerogpu_slot(
    hf_api: object,
    report: HardwareReport,
    exclude: set[str] | None = None,
) -> str | None:
    """Free a ZeroGPU slot by downgrading a paused Space to cpu-basic.

    Prefers Spaces that:
    1. Are paused (not actively running)
    2. Have 'cpu' in their name (likely don't need GPU)
    3. Are not in the exclude set

    Returns the space_id that was downgraded, or None if no slot freed.
    """
    exclude = exclude or set()
    candidates = [
        s for s in report.paused_zerogpu
        if s.space_id not in exclude
    ]
    if not candidates:
        return None

    # Prefer Spaces with 'cpu' in name, then any paused Space
    candidates.sort(key=lambda s: ("cpu" not in s.space_id.lower(), s.space_id))
    target = candidates[0]

    try:
        hf_api.request_space_hardware(target.space_id, "cpu-basic")  # type: ignore[attr-defined]
        report.freed_slots.append(target.space_id)
        logger.info("Freed ZeroGPU slot by downgrading %s to cpu-basic", target.space_id)
        return target.space_id
    except Exception as exc:
        report.errors.append(f"Failed to downgrade {target.space_id}: {exc}")
        logger.error("Failed to free ZeroGPU slot %s: %s", target.space_id, exc)
        return None


def request_zerogpu(
    hf_api: object,
    space_id: str,
    namespace: str,
    auto_free: bool = True,
    exclude: set[str] | None = None,
) -> tuple[bool, HardwareReport]:
    """Request ZeroGPU for a Space, auto-freeing a slot if needed.

    Args:
        hf_api: HuggingFace Hub API instance.
        space_id: Full Space ID (e.g. 'user/space-name').
        namespace: User or org namespace.
        auto_free: If True, automatically free a paused slot if limit reached.
        exclude: Set of space_ids to never downgrade.

    Returns:
        Tuple of (success, hardware_report).
    """
    report = build_hardware_report(hf_api, namespace)

    # Try direct request first
    try:
        hf_api.request_space_hardware(space_id, "zero-a10g")  # type: ignore[attr-defined]
        logger.info("ZeroGPU assigned to %s", space_id)
        return True, report
    except Exception as exc:
        if "limited to" not in str(exc).lower():
            report.errors.append(f"Unexpected error requesting ZeroGPU: {exc}")
            return False, report

    # Slots full - try to free one
    if not auto_free:
        report.errors.append(f"ZeroGPU slots full ({report.used_slots}/{report.total_slots}), auto_free disabled")
        return False, report

    freed = free_zerogpu_slot(hf_api, report, exclude=exclude)
    if not freed:
        report.errors.append("No paused ZeroGPU Spaces available to downgrade")
        return False, report

    # Retry after freeing
    try:
        hf_api.request_space_hardware(space_id, "zero-a10g")  # type: ignore[attr-defined]
        logger.info("ZeroGPU assigned to %s (after freeing %s)", space_id, freed)
        return True, report
    except Exception as exc:
        report.errors.append(f"Failed to assign ZeroGPU after freeing slot: {exc}")
        return False, report
