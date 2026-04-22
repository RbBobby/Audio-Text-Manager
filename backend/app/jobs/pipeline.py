from __future__ import annotations

import json
import logging
import time
import traceback
from pathlib import Path

from backend.app.asr import Transcriber
from backend.app.settings import Settings
from backend.app.summary import OllamaClient, OllamaError, Summarizer, parse_summary_size

from . import repository as repo

logger = logging.getLogger(__name__)

_M5_OLLAMA_METAL_HINT = (
    "Apple M5 + recent macOS: Ollama still runs ggml Metal init even with API num_gpu=0; "
    "Metal can fail in MPPTensorOpsMatMul2d (half/bfloat). This affects both the .app and "
    "Homebrew formula builds. Try starting the server with Metal tensor API disabled "
    "(must be set for the `ollama serve` process, e.g. in Terminal): "
    "GGML_METAL_TENSOR_DISABLE=1 ollama serve — then retry. "
    "Also upgrade Ollama when a release mentions M5/Metal fixes. "
    "https://github.com/ollama/ollama/issues/14432"
)

_transcribers: dict[tuple[bool, str], Transcriber] = {}


def _get_transcriber(settings: Settings) -> Transcriber:
    key = (
        settings.whisper_local_files_only,
        str(settings.whisper_download_root) if settings.whisper_download_root else "",
    )
    if key not in _transcribers:
        kwargs: dict = {"local_files_only": settings.whisper_local_files_only}
        if settings.whisper_download_root is not None:
            kwargs["download_root"] = settings.whisper_download_root
        _transcribers[key] = Transcriber(**kwargs)
        logger.info(
            "Whisper cache: local_files_only=%s download_root=%s",
            settings.whisper_local_files_only,
            settings.whisper_download_root,
        )
    return _transcribers[key]


def run_pipeline(job_id: str, settings: Settings) -> None:
    db = settings.sqlite_path
    row = repo.get_job(db, job_id)
    if not row or row["status"] != "processing":
        return

    audio = Path(row["audio_path"])
    preset = row["asr_preset"]
    summary_size = row["summary_size"]
    summarize_only = int(row.get("summarize_only") or 0)

    def fail(e: BaseException) -> None:
        row2 = repo.get_job(db, job_id)
        if not row2:
            return
        st = json.loads(row2["stages_json"])
        if row2.get("transcript"):
            st["summarize"] = "error"
            st["asr"] = "done"
        else:
            st["asr"] = "error"
        detail = f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}"
        if row2.get("transcript") and isinstance(e, OllamaError) and settings.apple_m5_cpu:
            detail = f"{detail}\n\n{_M5_OLLAMA_METAL_HINT}"
        detail = detail[:8000]
        logger.error("Job %s failed", job_id, exc_info=True)
        repo.clear_summarize_only_flag(db, job_id)
        repo.update_stages_and_optional(
            db,
            job_id,
            stages=st,
            status="error",
            error_message=detail,
        )

    try:
        if summarize_only:
            transcript_text = (row.get("transcript") or "").strip()
            if not transcript_text:
                raise ValueError("Empty transcript for summarize-only job")
            prev_timings = (
                json.loads(row["timings_json"]) if row.get("timings_json") else {}
            )
            asr_ms = int(prev_timings.get("asr_ms", 0))
            prev_mi = (
                json.loads(row["model_info_json"]) if row.get("model_info_json") else {}
            )
            whisper_model = str(prev_mi.get("whisper_model", "unknown"))
            language = prev_mi.get("asr_language")
            duration_sec = prev_mi.get("asr_duration_sec")
            logger.info(
                "Job %s summarize-only (skip ASR), transcript_len=%s",
                job_id,
                len(transcript_text),
            )
        else:
            if not audio.is_file():
                raise FileNotFoundError(f"Audio not found: {audio}")

            logger.info("Job %s ASR start preset=%s file=%s", job_id, preset, audio)
            t0 = time.perf_counter()
            tr = _get_transcriber(settings).transcribe(audio, preset)
            asr_ms = int((time.perf_counter() - t0) * 1000)
            transcript_text = tr.text
            whisper_model = tr.whisper_model
            language = tr.language
            duration_sec = tr.duration_sec

            st1 = {"upload": "done", "asr": "done", "summarize": "processing"}
            repo.update_stages_and_optional(
                db,
                job_id,
                stages=st1,
                transcript=transcript_text,
            )

        logger.info("Job %s summarize start size=%s summarize_only=%s", job_id, summary_size, summarize_only)
        t1 = time.perf_counter()
        ollama_opts: dict = {
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.ollama_num_predict,
        }
        if settings.ollama_num_gpu is not None:
            ollama_opts["num_gpu"] = settings.ollama_num_gpu
            logger.info(
                "Ollama options include num_gpu=%s (limits GPU offload; does not disable Metal)",
                settings.ollama_num_gpu,
            )
        if settings.apple_m5_cpu:
            logger.warning("Apple M5 + Ollama Metal: %s", _M5_OLLAMA_METAL_HINT)
        with OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            trust_env=settings.ollama_trust_env,
            default_options=ollama_opts,
        ) as client:
            summarizer = Summarizer(
                client,
                chunk_chars=settings.summary_chunk_chars,
                chunk_overlap=settings.summary_chunk_overlap,
                map_threshold_chars=settings.summary_map_threshold_chars,
                max_input_chars=settings.summarizer_max_input_chars,
                max_reduce_chars=settings.summarizer_max_reduce_chars,
                map_chunk_max_chars=settings.summarizer_map_chunk_max_chars,
                ollama_num_ctx=settings.ollama_num_ctx,
                ollama_num_predict=settings.ollama_num_predict,
            )
            nominal = parse_summary_size(str(summary_size).strip())
            cp = (row.get("custom_prompt") or "").strip()
            if cp:
                sr = summarizer.summarize_custom_prompt(
                    transcript_text, cp, nominal_size=nominal
                )
            else:
                sr = summarizer.summarize(transcript_text, summary_size)
        sum_ms = int((time.perf_counter() - t1) * 1000)

        st2 = {"upload": "done", "asr": "done", "summarize": "done"}
        timings = {"asr_ms": asr_ms, "summarize_ms": sum_ms}
        model_info: dict = {
            "asr_preset": preset,
            "whisper_model": whisper_model,
            "summary_size": summary_size,
            "ollama_model": settings.ollama_model,
            "summary_mode": sr.mode,
            "summary_source_chunks": sr.source_chunks,
            "asr_language": language,
            "asr_duration_sec": duration_sec,
            "ollama_num_gpu": settings.ollama_num_gpu,
            "ollama_homebrew_formula": settings.ollama_homebrew_formula,
            "apple_m5_cpu": settings.apple_m5_cpu,
        }
        if summarize_only:
            model_info["summarize_only_rerun"] = True
        repo.update_stages_and_optional(
            db,
            job_id,
            stages=st2,
            status="done",
            summary=sr.text,
            timings=timings,
            model_info=model_info,
        )
        repo.clear_summarize_only_flag(db, job_id)
        logger.info(
            "Job %s completed summarize_ms=%s mode=%s source_chunks=%s summarize_only=%s",
            job_id,
            sum_ms,
            sr.mode,
            sr.source_chunks,
            summarize_only,
        )
    except Exception as e:
        fail(e)
