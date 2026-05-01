from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PatchAction = Literal["create", "update", "delete", "suggest"]


class RepairPatch(BaseModel):
    file_path: str
    action: PatchAction = "suggest"
    patch_summary: str
    safe_to_apply: bool = True
    generated_by: str = "selfrepair-local"
    prompt: str | None = None
    content_preview: str | None = Field(default=None, max_length=2000)
