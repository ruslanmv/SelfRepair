def is_safe_fix(changed_files: list[str], max_files: int) -> bool:
    return len(changed_files) <= max_files
