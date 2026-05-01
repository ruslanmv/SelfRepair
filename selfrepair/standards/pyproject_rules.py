from __future__ import annotations

from pathlib import Path

DEFAULT_PYPROJECT = """[build-system]
requires = [\"setuptools>=69\", \"wheel\"]
build-backend = \"setuptools.build_meta\"

[project]
name = \"app\"
version = \"0.1.0\"
description = \"Managed by SelfRepair Repo\"
requires-python = \">=3.11,<3.13\"
dependencies = []

[tool.uv]
"""


def ensure_pyproject(repo_dir: Path, project_name: str) -> tuple[bool, list[str]]:
    changed: list[str] = []
    path = repo_dir / "pyproject.toml"
    if not path.exists():
        path.write_text(DEFAULT_PYPROJECT.replace('name = "app"', f'name = "{project_name}"'), encoding="utf-8")
        changed.append("pyproject.toml")
        return True, changed

    text = path.read_text(encoding="utf-8")
    updated = text
    if "requires-python" not in updated:
        updated += '\n[project]\nrequires-python = ">=3.11,<3.13"\n'
    elif "3.11" not in updated:
        lines = []
        for line in updated.splitlines():
            if line.strip().startswith("requires-python"):
                lines.append('requires-python = ">=3.11,<3.13"')
            else:
                lines.append(line)
        updated = "\n".join(lines) + ("\n" if updated.endswith("\n") else "")
    if "[tool.uv]" not in updated:
        updated += "\n[tool.uv]\n"
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        changed.append("pyproject.toml")
    return True, changed
