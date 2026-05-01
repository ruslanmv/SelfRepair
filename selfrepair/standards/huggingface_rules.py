from __future__ import annotations

from pathlib import Path

from selfrepair.models import RepoRef

README_TEMPLATE = """---
license: apache-2.0
library_name: selfrepair
pipeline_tag: text-classification
---

# {title}

Maintained by SelfRepair Repo.
"""


def ensure_huggingface_metadata(repo_dir: Path, repo: RepoRef) -> tuple[bool, list[str]]:
    changed: list[str] = []
    readme = repo_dir / "README.md"
    if repo.platform != "huggingface":
        return True, changed
    if not readme.exists():
        readme.write_text(README_TEMPLATE.format(title=repo.name), encoding="utf-8")
        changed.append("README.md")
        return True, changed
    text = readme.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        readme.write_text(README_TEMPLATE.format(title=repo.name) + "\n" + text, encoding="utf-8")
        changed.append("README.md")
    return True, changed
