from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment, TranscriptionInfo

from .ffmpeg_normalize import normalize_audio_for_whisper
from .presets import ASRPreset, parse_asr_preset, whisper_model_name


@dataclass(frozen=True)
class TranscribeResult:
    text: str
    language: str
    language_probability: float
    duration_sec: float
    duration_after_vad_sec: float
    whisper_model: str
    preset: ASRPreset
    segments: list[dict[str, Any]]


class Transcriber:
    """faster-whisper ASR with ffmpeg preprocessing and fast/medium/high presets."""

    def __init__(
        self,
        *,
        device: str = "auto",
        compute_type: str = "default",
        download_root: Path | str | None = None,
        local_files_only: bool = False,
        cpu_threads: int = 0,
        num_workers: int = 1,
    ) -> None:
        self._device = device
        self._compute_type = compute_type
        self._download_root = str(download_root) if download_root else None
        self._local_files_only = local_files_only
        self._cpu_threads = cpu_threads
        self._num_workers = num_workers
        self._models: dict[str, WhisperModel] = {}

    def _model(self, preset: ASRPreset) -> WhisperModel:
        name = whisper_model_name(preset)
        if name not in self._models:
            self._models[name] = WhisperModel(
                name,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._download_root,
                local_files_only=self._local_files_only,
                cpu_threads=self._cpu_threads,
                num_workers=self._num_workers,
            )
        return self._models[name]

    def _transcribe_path(
        self,
        model: WhisperModel,
        input_path: Path,
        *,
        language: str | None,
        beam_size: int,
        vad_filter: bool,
        word_timestamps: bool,
        vad_parameters: Any | None,
        log_progress: bool,
    ) -> tuple[list[Segment], TranscriptionInfo]:
        segments_iter, info = model.transcribe(
            str(input_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            vad_parameters=vad_parameters,
            log_progress=log_progress,
        )
        return list(segments_iter), info

    @staticmethod
    def _segments_to_result(
        preset: ASRPreset,
        whisper_model: str,
        segments: list[Segment],
        info: TranscriptionInfo,
    ) -> TranscribeResult:
        parts: list[str] = []
        out: list[dict[str, Any]] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if text:
                parts.append(text)
            out.append({"start": seg.start, "end": seg.end, "text": seg.text})
        return TranscribeResult(
            text=" ".join(parts),
            language=info.language,
            language_probability=info.language_probability,
            duration_sec=info.duration,
            duration_after_vad_sec=info.duration_after_vad,
            whisper_model=whisper_model,
            preset=preset,
            segments=out,
        )

    def transcribe(
        self,
        audio_path: str | Path,
        preset: str | ASRPreset,
        *,
        normalize: bool = True,
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        word_timestamps: bool = False,
        vad_parameters: Any | None = None,
        log_progress: bool = False,
    ) -> TranscribeResult:
        audio_path = Path(audio_path)
        if isinstance(preset, str):
            preset = parse_asr_preset(preset)
        model = self._model(preset)
        wname = whisper_model_name(preset)

        if normalize:
            with tempfile.TemporaryDirectory(prefix="atm_asr_") as tmp:
                wav = Path(tmp) / "normalized.wav"
                normalize_audio_for_whisper(audio_path, wav)
                segments, info = self._transcribe_path(
                    model,
                    wav,
                    language=language,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                    word_timestamps=word_timestamps,
                    vad_parameters=vad_parameters,
                    log_progress=log_progress,
                )
        else:
            segments, info = self._transcribe_path(
                model,
                audio_path,
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
                vad_parameters=vad_parameters,
                log_progress=log_progress,
            )

        return self._segments_to_result(preset, wname, segments, info)
