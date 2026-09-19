from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def audio_duration_seconds(path: Path) -> float | None:
    """Return media duration in seconds via ffprobe, or None if unavailable."""
    if not shutil.which("ffprobe"):
        logger.warning("ffprobe not found; duration checks are skipped")
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out for %s", path)
        return None
    if completed.returncode != 0:
        logger.warning(
            "ffprobe failed (%s): %s",
            completed.returncode,
            (completed.stderr or completed.stdout or "").strip()[:500],
        )
        return None
    out = (completed.stdout or "").strip()
    if not out:
        return None
    try:
        return float(out)
    except ValueError:
        logger.warning("ffprobe returned non-float duration: %r", out[:80])
        return None


def has_audio_stream(path: Path) -> bool | None:
    """Return True if the file has an audio stream, False if none, None if ffprobe fails."""
    if not shutil.which("ffprobe"):
        logger.warning("ffprobe not found; audio-stream checks are skipped")
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out while checking audio streams for %s", path)
        return None
    if completed.returncode != 0:
        logger.warning(
            "ffprobe audio-stream check failed (%s): %s",
            completed.returncode,
            (completed.stderr or completed.stdout or "").strip()[:500],
        )
        return None
    return bool((completed.stdout or "").strip())
