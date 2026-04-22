from __future__ import annotations

from typing import Literal

SummarySize = Literal["gist", "executive", "meeting"]

_LEGACY_SUMMARY: dict[str, SummarySize] = {
    "short": "gist",
    "medium": "executive",
    "long": "meeting",
}


def parse_summary_size(value: str) -> SummarySize:
    v = value.strip().lower()
    v = _LEGACY_SUMMARY.get(v, v)
    if v not in ("gist", "executive", "meeting"):
        raise ValueError(
            f"Invalid summary size {value!r}; expected one of: gist, executive, meeting "
            f"(legacy aliases: short, medium, long)"
        )
    return v  # type: ignore[return-value]
