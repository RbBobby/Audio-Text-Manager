from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _darwin_cpu_brand() -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            text=True,
            timeout=2,
        )
        return out.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _resolve_ollama_num_gpu(*, cpu_brand: str) -> int | None:
    """
    Ollama /api/chat option num_gpu: limits how many layers use the GPU.

    On Apple Silicon, num_gpu=0 still loads the Metal backend for the llama context
    (weights may stay on CPU). For M5 + broken Metal, the real fix is usually an
    official Ollama build (cask), not this flag alone — see issue #14432.
    """
    if _truthy("ATM_OLLAMA_ALLOW_METAL"):
        return None
    raw = os.environ.get("ATM_OLLAMA_NUM_GPU", "").strip()
    if raw != "":
        try:
            return max(0, min(int(raw), 256))
        except ValueError:
            pass
    if cpu_brand and re.search(r"\bM5\b", cpu_brand):
        return 0
    return None


def ollama_binary_looks_like_homebrew_formula() -> bool:
    """
    True if `ollama` on PATH resolves under Homebrew Cellar (formula build).

    That build is often compiled against the host Metal SDK and can hit M5
    shader static_assert failures; the cask / ollama.com binary usually works.
    """
    which = shutil.which("ollama")
    if not which:
        return False
    try:
        resolved = Path(which).resolve()
    except OSError:
        return False
    parts = resolved.parts
    return "Cellar" in parts and "ollama" in parts


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sqlite_path: Path
    uploads_dir: Path
    ollama_base_url: str
    ollama_model: str
    max_upload_bytes: int
    summary_chunk_chars: int
    summary_chunk_overlap: int
    summary_map_threshold_chars: int
    log_level: str
    offline_mode: bool
    whisper_local_files_only: bool
    whisper_download_root: Path | None
    max_audio_duration_sec: int
    ollama_trust_env: bool
    ollama_num_ctx: int
    ollama_num_predict: int
    summarizer_max_input_chars: int
    summarizer_max_reduce_chars: int
    summarizer_map_chunk_max_chars: int
    ollama_num_gpu: int | None
    apple_m5_cpu: bool
    ollama_homebrew_formula: bool

    @staticmethod
    def from_env() -> Settings:
        root = Path(os.environ.get("ATM_DATA_DIR", "data")).resolve()
        offline = _truthy("ATM_OFFLINE")
        whisper_root_raw = os.environ.get("ATM_WHISPER_DOWNLOAD_ROOT", "").strip()
        whisper_download = (
            Path(whisper_root_raw).resolve() if whisper_root_raw else None
        )
        max_dur_raw = os.environ.get("ATM_MAX_AUDIO_DURATION_SEC", "0").strip()
        try:
            max_audio_duration_sec = int(max_dur_raw)
        except ValueError:
            max_audio_duration_sec = 0

        def _i(name: str, default: int, *, min_v: int = 0, max_v: int | None = None) -> int:
            try:
                v = int(os.environ.get(name, str(default)).strip())
            except ValueError:
                v = default
            v = max(min_v, v)
            if max_v is not None:
                v = min(max_v, v)
            return v

        ollama_num_ctx = _i("ATM_OLLAMA_NUM_CTX", 8192, min_v=512, max_v=262144)
        # Lower default leaves more context room for input vs output (long summaries → raise env).
        ollama_num_predict = _i("ATM_OLLAMA_NUM_PREDICT", 2048, min_v=256, max_v=131072)
        summarizer_max_input_chars = _i(
            "ATM_SUMMARIZER_MAX_INPUT_CHARS", 80_000, min_v=0, max_v=2_000_000
        )
        summarizer_max_reduce_chars = _i(
            "ATM_SUMMARIZER_MAX_REDUCE_CHARS", 24_000, min_v=2000, max_v=500_000
        )
        summarizer_map_chunk_max_chars = _i(
            "ATM_SUMMARIZER_MAP_CHUNK_MAX_CHARS", 8000, min_v=1000, max_v=100_000
        )
        cpu_brand = _darwin_cpu_brand()
        apple_m5_cpu = bool(cpu_brand and re.search(r"\bM5\b", cpu_brand))
        ollama_num_gpu = _resolve_ollama_num_gpu(cpu_brand=cpu_brand)
        ollama_homebrew_formula = ollama_binary_looks_like_homebrew_formula()

        return Settings(
            data_dir=root,
            sqlite_path=Path(
                os.environ.get("ATM_SQLITE_PATH", str(root / "app.db"))
            ).resolve(),
            uploads_dir=Path(
                os.environ.get("ATM_UPLOADS_DIR", str(root / "uploads"))
            ).resolve(),
            ollama_base_url=os.environ.get(
                "ATM_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
            ),
            ollama_model=os.environ.get(
                "ATM_OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M"
            ),
            max_upload_bytes=int(
                os.environ.get("ATM_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024))
            ),
            summary_chunk_chars=int(os.environ.get("ATM_SUMMARY_CHUNK_CHARS", "10000")),
            summary_chunk_overlap=int(
                os.environ.get("ATM_SUMMARY_CHUNK_OVERLAP", "400")
            ),
            summary_map_threshold_chars=int(
                os.environ.get("ATM_SUMMARY_MAP_THRESHOLD", "12000")
            ),
            log_level=os.environ.get("ATM_LOG_LEVEL", "INFO").upper(),
            offline_mode=offline,
            whisper_local_files_only=offline or _truthy("ATM_WHISPER_LOCAL_ONLY"),
            whisper_download_root=whisper_download,
            max_audio_duration_sec=max(0, max_audio_duration_sec),
            ollama_trust_env=not offline and not _truthy("ATM_OLLAMA_DISABLE_TRUST_ENV"),
            ollama_num_ctx=ollama_num_ctx,
            ollama_num_predict=ollama_num_predict,
            summarizer_max_input_chars=summarizer_max_input_chars,
            summarizer_max_reduce_chars=summarizer_max_reduce_chars,
            summarizer_map_chunk_max_chars=summarizer_map_chunk_max_chars,
            ollama_num_gpu=ollama_num_gpu,
            apple_m5_cpu=apple_m5_cpu,
            ollama_homebrew_formula=ollama_homebrew_formula,
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
