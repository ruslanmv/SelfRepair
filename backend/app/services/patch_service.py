from __future__ import annotations

from pathlib import Path


class PatchService:
    """Writes safe local patch content when explicitly requested."""

    def apply_text_patch(self, repo_path: str, relative_path: str, content: str) -> dict:
        repo_dir = Path(repo_path).resolve()
        target = (repo_dir / relative_path).resolve()
        if not str(target).startswith(str(repo_dir)):
            raise ValueError("Patch path escapes repository workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = target.read_text(encoding="utf-8") if target.exists() else None
        target.write_text(content, encoding="utf-8")
        return {
            "repo_path": str(repo_dir),
            "file_path": relative_path,
            "created": previous is None,
            "status": "applied",
        }
