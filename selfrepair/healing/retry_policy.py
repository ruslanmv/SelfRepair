from __future__ import annotations


def should_retry(attempt: int, max_fix_attempts: int) -> bool:
    return attempt < max_fix_attempts
