from __future__ import annotations

import pytest

from backend.app.asr import parse_asr_preset, whisper_model_name
from backend.app.summary import parse_summary_size


@pytest.mark.parametrize(
    ("preset", "model"),
    [
        ("fast", "small"),
        ("medium", "medium"),
        ("high", "large-v3"),
    ],
)
def test_asr_preset_mapping(preset: str, model: str) -> None:
    p = parse_asr_preset(preset)
    assert whisper_model_name(p) == model


@pytest.mark.parametrize("size", ("gist", "executive", "meeting"))
def test_summary_sizes(size: str) -> None:
    assert parse_summary_size(size) == size


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("short", "gist"),
        ("medium", "executive"),
        ("long", "meeting"),
    ],
)
def test_summary_size_legacy_aliases(legacy: str, expected: str) -> None:
    assert parse_summary_size(legacy) == expected


def test_invalid_summary_size() -> None:
    with pytest.raises(ValueError):
        parse_summary_size("huge")


def test_invalid_asr() -> None:
    with pytest.raises(ValueError):
        parse_asr_preset("tiny")
