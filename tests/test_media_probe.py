from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from backend.app.media_probe import audio_duration_seconds


@pytest.fixture
def tiny_wav(tmp_path: Path) -> Path:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.25",
            str(out),
        ],
        check=True,
    )
    return out


def test_audio_duration_positive(tiny_wav: Path) -> None:
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed")
    d = audio_duration_seconds(tiny_wav)
    assert d is not None
    assert 0.2 < d < 1.5
