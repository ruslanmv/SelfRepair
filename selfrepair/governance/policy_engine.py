from __future__ import annotations


def evaluate_policy(changed_files: list[str]) -> dict[str, str | int]:
    count = len(changed_files)
    risk = "low" if count <= 5 else "medium" if count <= 15 else "high"
    return {"risk": risk, "changed_files": count}
