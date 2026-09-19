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


def _write_mp4(path: Path, *, with_audio: bool) -> None:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=160x120:d=0.25",
    ]
    if with_audio:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.25",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-shortest",
            ]
        )
    else:
        cmd.extend(["-an", "-c:v", "mpeg4"])
    cmd.append(str(path))
    subprocess.run(cmd, check=True)


def test_mp4_duration_and_audio_stream(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed")
    from backend.app.media_probe import has_audio_stream

    with_audio = tmp_path / "with.mp4"
    silent = tmp_path / "silent.mp4"
    _write_mp4(with_audio, with_audio=True)
    _write_mp4(silent, with_audio=False)
    d = audio_duration_seconds(with_audio)
    assert d is not None
    assert 0.1 < d < 2.0
    assert has_audio_stream(with_audio) is True
    assert has_audio_stream(silent) is False


def test_normalize_mp4_extracts_audio_wav(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src = tmp_path / "clip.mp4"
    _write_mp4(src, with_audio=True)
    from backend.app.asr.ffmpeg_normalize import normalize_audio_for_whisper

    dst = tmp_path / "out.wav"
    normalize_audio_for_whisper(src, dst)
    assert dst.is_file()
    assert dst.stat().st_size > 0
