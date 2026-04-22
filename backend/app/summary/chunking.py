from __future__ import annotations


def chunk_transcript(
    text: str,
    *,
    max_chars: int = 10_000,
    overlap: int = 400,
) -> list[str]:
    """Split transcript into overlapping chunks for map-reduce."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            end = _prefer_break(text, start, end)
        chunk = text[start:end].strip()
        if not chunk:
            if end >= n:
                break
            start = end
            continue
        chunks.append(chunk)
        if end >= n:
            break
        start = max(start + 1, end - overlap)
    return chunks


def _prefer_break(text: str, start: int, end: int) -> int:
    """Nudge end backward to a paragraph or sentence boundary when possible."""
    window = text[start:end]
    min_keep = int(len(window) * 0.45)

    for sep in ("\n\n", "\n", ". ", "。", "! ", "? "):
        idx = window.rfind(sep)
        if idx >= min_keep:
            return start + idx + len(sep)

    return end
