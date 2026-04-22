from __future__ import annotations

from .presets import SummarySize


def system_instruction_final(size: SummarySize) -> str:
    """System-style instruction for the final summary shape (single-shot or reduce)."""
    if size == "short":
        return (
            "You summarize transcripts. Output 5–7 bullet points (use '-' or '•'). "
            "Stay faithful to the source. Write in the same language as the transcript."
        )
    if size == "medium":
        return (
            "You summarize transcripts. Output 2–4 coherent paragraphs, then a section "
            "titled exactly 'Action items:' with bullet points for concrete next steps or "
            "decisions. Write in the same language as the transcript."
        )
    return (
        "You summarize transcripts as a detailed structured outline. Use markdown "
        "headings (##) for major sections and subsections where helpful. Cover important "
        "facts, arguments, and conclusions. Write in the same language as the transcript."
    )


def system_instruction_map() -> str:
    return (
        "You extract key information from a transcript excerpt. Produce a compact factual "
        "summary: main topics, entities, decisions, dates, numbers, and any action items "
        "mentioned in this excerpt only. No preamble. Write in the same language as the excerpt."
    )


def user_map_chunk(chunk: str) -> str:
    return f"--- Transcript excerpt ---\n{chunk}\n--- End excerpt ---\n\nSummarize this excerpt."


def user_single_shot(transcript: str) -> str:
    return f"--- Transcript ---\n{transcript}\n--- End transcript ---\n\nProduce the summary."


def user_reduce(partials: list[str], size: SummarySize) -> str:
    body = "\n\n".join(
        f"--- Partial summary {i + 1} ---\n{p.strip()}" for i, p in enumerate(partials) if p.strip()
    )
    if size == "short":
        goal = "Merge into one coherent list of 5–7 bullet points. Remove redundancy."
    elif size == "medium":
        goal = (
            "Merge into 2–4 paragraphs plus an 'Action items:' bullet list. "
            "Unify overlapping content; keep one clear narrative."
        )
    else:
        goal = (
            "Merge into one structured long outline with ## headings. "
            "Deduplicate; preserve important detail from all parts."
        )
    return (
        f"You are given partial summaries from consecutive parts of ONE transcript.\n"
        f"{goal}\n\n{body}\n\n--- End partial summaries ---\n\nProduce the final summary."
    )
