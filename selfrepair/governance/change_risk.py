def classify_change_risk(changed_files: list[str]) -> str:
    if not changed_files:
        return "none"
    if len(changed_files) <= 3 and all(x.endswith((".toml", ".py")) or x == "Makefile" for x in changed_files):
        return "low"
    if len(changed_files) <= 10:
        return "medium"
    return "high"
