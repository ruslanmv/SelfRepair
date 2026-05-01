from pathlib import Path

def makefile_has_start(makefile_path: Path) -> bool:
    if not makefile_path.exists():
        return False
    return "\nstart:" in "\n" + makefile_path.read_text(encoding="utf-8")
