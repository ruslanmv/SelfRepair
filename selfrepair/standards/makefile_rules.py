from __future__ import annotations

from pathlib import Path

DEFAULT_MAKEFILE = """.PHONY: install test start

install:
\tpython -m pip install -U pip >/dev/null 2>&1 || true
\tif [ -f requirements.txt ]; then python -m pip install -r requirements.txt; elif [ -f pyproject.toml ]; then python -m pip install -e .; else echo 'nothing to install'; fi

test:
\tif [ -d tests ]; then python -m pytest -q; else python -c \"print('no tests directory')\"; fi

start:
\tpython -c \"print('selfrepair smoke start ok')\"
"""


def ensure_makefile(repo_dir: Path) -> tuple[bool, list[str]]:
    changed: list[str] = []
    makefile = repo_dir / "Makefile"
    if not makefile.exists():
        makefile.write_text(DEFAULT_MAKEFILE, encoding="utf-8")
        changed.append("Makefile")
        return True, changed

    text = makefile.read_text(encoding="utf-8")
    updated = text
    if "install:" not in updated:
        updated += "\ninstall:\n\tpython -m pip install -U pip >/dev/null 2>&1 || true\n"
    if "test:" not in updated:
        updated += "\ntest:\n\tif [ -d tests ]; then python -m pytest -q; else python -c \"print('no tests directory')\"; fi\n"
    if "start:" not in updated:
        updated += "\nstart:\n\tpython -c \"print('selfrepair smoke start ok')\"\n"
    if updated != text:
        makefile.write_text(updated, encoding="utf-8")
        changed.append("Makefile")
    return True, changed
