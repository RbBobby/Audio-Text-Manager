from __future__ import annotations

from typing import Literal

SummarySize = Literal["long", "medium", "short"]


def parse_summary_size(value: str) -> SummarySize:
    v = value.strip().lower()
    if v not in ("long", "medium", "short"):
        raise ValueError(
            f"Invalid summary size {value!r}; expected one of: long, medium, short"
        )
    return v  # type: ignore[return-value]
