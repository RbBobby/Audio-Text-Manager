from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    def __init__(self, message: str, *, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ensure_ffmpeg() -> None:
    if not ffmpeg_available():
        raise FFmpegError("ffmpeg is not installed or not on PATH")


def normalize_audio_for_whisper(src: Path, dst: Path) -> Path:
    """Convert audio (or the first audio track of a video) to mono 16 kHz PCM WAV."""
    ensure_ffmpeg()
    src = Path(src)
    dst = Path(dst)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src.resolve()),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dst.resolve()),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or "unknown error"
        lower = detail.lower()
        if "matches no streams" in lower or "does not contain any stream" in lower:
            raise FFmpegError(
                "No audio track in file; cannot transcribe",
                stderr=completed.stderr,
            )
        raise FFmpegError(
            f"ffmpeg failed (exit {completed.returncode}): {detail}",
            stderr=completed.stderr,
        )
    if not dst.is_file():
        raise FFmpegError("ffmpeg reported success but the output file is missing")
    return dst
