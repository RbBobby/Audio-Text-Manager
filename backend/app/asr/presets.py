from __future__ import annotations

from typing import Literal

ASRPreset = Literal["fast", "medium", "high"]

_PRESET_TO_MODEL: dict[ASRPreset, str] = {
    "fast": "small",
    "medium": "medium",
    "high": "large-v3",
}


def whisper_model_name(preset: ASRPreset) -> str:
    return _PRESET_TO_MODEL[preset]


def parse_asr_preset(value: str) -> ASRPreset:
    v = value.strip().lower()
    if v not in _PRESET_TO_MODEL:
        allowed = ", ".join(sorted(_PRESET_TO_MODEL))
        raise ValueError(f"Invalid ASR preset {value!r}; expected one of: {allowed}")
    return v  # type: ignore[return-value]
