from __future__ import annotations


def clip_head_tail(text: str, max_chars: int) -> str:
    """Keep start and end of long text so prompts stay within rough context limits."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    marker = "\n\n[... omitted middle of text ...]\n\n"
    budget = max_chars - len(marker)
    if budget < 80:
        return text[:max_chars]
    head = budget // 2
    tail = budget - head
    return text[:head] + marker + text[-tail:]
