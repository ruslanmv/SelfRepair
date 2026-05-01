def truncate(text: str, max_len: int = 2000) -> str:
    return text if len(text) <= max_len else text[:max_len] + "\n...[truncated]"
