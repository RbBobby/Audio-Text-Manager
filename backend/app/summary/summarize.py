from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from .chunking import chunk_transcript
from .ollama import OllamaClient, OllamaError
from .presets import SummarySize, parse_summary_size
from .prompts import (
    system_instruction_final,
    system_instruction_map,
    user_map_chunk,
    user_reduce,
    user_single_shot,
)
from .text_clip import clip_head_tail

DEFAULT_MAP_THRESHOLD_CHARS = 12_000

logger = logging.getLogger(__name__)


def _prompt_char_budget(num_ctx: int, num_predict: int) -> int:
    """
    Rough max chars for user+system prompts so Ollama stays within num_ctx.
    Heuristic ~3 chars/token; leaves num_predict + overhead for generation.
    """
    overhead = num_predict + 900
    room = max(256, num_ctx - overhead)
    return max(1200, min(80_000, room * 3))


@dataclass(frozen=True)
class SummaryResult:
    text: str
    size: SummarySize
    model: str
    mode: Literal["single", "map_reduce", "custom"]
    source_chunks: int


class Summarizer:
    """Local LLM summarization via Ollama: gist / executive / meeting presets and map-reduce."""

    def __init__(
        self,
        client: OllamaClient,
        *,
        chunk_chars: int = 10_000,
        chunk_overlap: int = 400,
        map_threshold_chars: int = DEFAULT_MAP_THRESHOLD_CHARS,
        max_input_chars: int = 0,
        max_reduce_chars: int = 28_000,
        map_chunk_max_chars: int = 8000,
        ollama_num_ctx: int = 8192,
        ollama_num_predict: int = 2048,
    ) -> None:
        self._client = client
        budget = _prompt_char_budget(ollama_num_ctx, ollama_num_predict)
        self._max_reduce_chars = max(1200, min(max_reduce_chars, budget))
        map_cap = max(900, min(map_chunk_max_chars, self._max_reduce_chars // 2 - 400))
        self._map_chunk_max = map_cap
        self._chunk_chars = max(500, min(chunk_chars, map_cap))
        self._chunk_overlap = min(chunk_overlap, max(100, self._chunk_chars // 2))
        self._map_threshold = map_threshold_chars
        self._max_input_chars = max(0, max_input_chars)
        # If transcript is longer than fits in one user message, use map-reduce.
        self._single_shot_char_limit = max(800, self._max_reduce_chars - 600)
        self._ollama_num_ctx = ollama_num_ctx
        self._ollama_num_predict = ollama_num_predict
        self._adaptive_max_rounds = 8
        self._prompt_budget_chars = _prompt_char_budget(ollama_num_ctx, ollama_num_predict)
        logger.debug(
            "Summarizer limits: ctx=%s predict=%s budget_chars=%s max_reduce=%s "
            "map_chunk=%s chunk=%s single_shot_limit=%s",
            ollama_num_ctx,
            ollama_num_predict,
            budget,
            self._max_reduce_chars,
            self._map_chunk_max,
            self._chunk_chars,
            self._single_shot_char_limit,
        )

    def summarize_custom_prompt(
        self, transcript: str, custom_prompt: str, *, nominal_size: SummarySize
    ) -> SummaryResult:
        """Single Ollama chat: fixed system message + user = instructions + transcript (clipped)."""
        instr = (custom_prompt or "").strip()
        if not instr:
            return SummaryResult(
                text="",
                size=nominal_size,
                model=self._client.model,
                mode="custom",
                source_chunks=0,
            )
        txt = transcript.strip()
        reserve = len(instr) + 120
        max_trans = max(500, self._prompt_budget_chars - reserve)
        if len(txt) > max_trans:
            logger.warning(
                "Custom prompt path: clipping transcript %d -> %d chars for context",
                len(txt),
                max_trans,
            )
            txt = clip_head_tail(txt, max_trans)
        body = f"{instr}\n\n--- Транскрипт ---\n{txt}"
        if len(body) > self._max_reduce_chars:
            body = clip_head_tail(body, self._max_reduce_chars)
        messages = [
            {
                "role": "system",
                "content": (
                    "You follow the user's instructions precisely. "
                    "Answer in the same language as the transcript unless asked otherwise."
                ),
            },
            {"role": "user", "content": body},
        ]
        out = self._adaptive_chat(messages, tag="summary-custom")
        return SummaryResult(
            text=out.strip(),
            size=nominal_size,
            model=self._client.model,
            mode="custom",
            source_chunks=1,
        )

    def _adaptive_chat(
        self,
        messages: list[dict[str, str]],
        *,
        tag: str = "ollama",
    ) -> str:
        """Lower num_ctx/num_predict on runner OOM / 5xx until request succeeds."""
        ctx = self._ollama_num_ctx
        pred = self._ollama_num_predict
        work: list[dict[str, str]] = [{"role": m["role"], "content": m["content"]} for m in messages]

        def _retryable(err: OllamaError) -> bool:
            s = str(err).lower()
            return (
                "500" in str(err)
                or "502" in str(err)
                or "503" in str(err)
                or "504" in str(err)
                or "terminated" in s
                or "runner" in s
                or "process has" in s
                or "oom" in s
                or "cuda" in s
                or "metal" in s
            )

        for attempt in range(self._adaptive_max_rounds):
            pred = min(pred, max(128, ctx - 384))
            opts = {"num_ctx": ctx, "num_predict": pred}
            try:
                return self._client.chat(work, options=opts).strip()
            except OllamaError as e:
                if not _retryable(e) or attempt == self._adaptive_max_rounds - 1:
                    logger.error("%s failed after %s rounds: %s", tag, attempt + 1, e)
                    raise
                nctx = max(512, int(ctx * 0.62))
                npred = max(128, int(pred * 0.62))
                if nctx >= ctx and npred >= pred:
                    npred = max(128, pred - 200)
                ctx, pred = nctx, npred
                logger.warning(
                    "%s adaptive round %s/%s num_ctx=%s num_predict=%s err=%s",
                    tag,
                    attempt + 1,
                    self._adaptive_max_rounds,
                    ctx,
                    pred,
                    e,
                )
            if attempt >= 4 and work[-1]["role"] == "user" and len(work[-1]["content"]) > 2500:
                lim = max(2000, int(len(work[-1]["content"]) * 0.45))
                logger.warning("%s shrinking user message to %s chars", tag, lim)
                work[-1] = {
                    **work[-1],
                    "content": clip_head_tail(work[-1]["content"], lim),
                }

    def summarize(
        self,
        transcript: str,
        size: str | SummarySize,
        *,
        force_single: bool = False,
        force_map_reduce: bool = False,
    ) -> SummaryResult:
        if isinstance(size, str):
            size = parse_summary_size(size)
        text = transcript.strip()
        if not text:
            return SummaryResult(
                text="",
                size=size,
                model=self._client.model,
                mode="single",
                source_chunks=0,
            )

        if self._max_input_chars > 0 and len(text) > self._max_input_chars:
            logger.warning(
                "Transcript clipped from %d to %d chars before LLM",
                len(text),
                self._max_input_chars,
            )
            text = clip_head_tail(text, self._max_input_chars)

        if force_single and force_map_reduce:
            force_map_reduce = False

        want_map = force_map_reduce or (
            not force_single
            and (
                len(text) > self._map_threshold
                or len(text) > self._single_shot_char_limit
            )
        )
        if want_map and len(text) <= self._map_threshold:
            logger.info(
                "Using map-reduce: transcript %d chars exceeds single-shot budget %d "
                "(num_ctx=%d num_predict=%d)",
                len(text),
                self._single_shot_char_limit,
                self._ollama_num_ctx,
                self._ollama_num_predict,
            )

        if not want_map:
            return self._single(text, size)

        chunks = chunk_transcript(
            text,
            max_chars=self._chunk_chars,
            overlap=self._chunk_overlap,
        )
        if len(chunks) <= 1:
            return self._single(text, size)

        return self._map_reduce(chunks, size)

    def _single(self, transcript: str, size: SummarySize) -> SummaryResult:
        body = user_single_shot(transcript)
        if len(body) > self._max_reduce_chars:
            logger.warning(
                "Single-shot prompt clipped from %d to %d chars",
                len(body),
                self._max_reduce_chars,
            )
            body = clip_head_tail(body, self._max_reduce_chars)
        messages = [
            {"role": "system", "content": system_instruction_final(size)},
            {"role": "user", "content": body},
        ]
        try:
            out = self._adaptive_chat(messages, tag="summary-single")
        except OllamaError:
            logger.warning(
                "Single-shot failed after adaptive retries; trying map-reduce fallback"
            )
            sub = chunk_transcript(
                transcript,
                max_chars=max(1000, self._chunk_chars // 3),
                overlap=max(60, self._chunk_chars // 25),
            )
            if len(sub) > 1:
                return self._map_reduce(sub, size)
            tight = clip_head_tail(
                transcript, max(1200, self._max_reduce_chars // 2 - 200)
            )
            body2 = user_single_shot(tight)
            if len(body2) > self._max_reduce_chars:
                body2 = clip_head_tail(body2, self._max_reduce_chars)
            messages2 = [
                {"role": "system", "content": system_instruction_final(size)},
                {"role": "user", "content": body2},
            ]
            out = self._adaptive_chat(messages2, tag="summary-single-tight")
        return SummaryResult(
            text=out,
            size=size,
            model=self._client.model,
            mode="single",
            source_chunks=1,
        )

    def _map_reduce(self, chunks: list[str], size: SummarySize) -> SummaryResult:
        sys_map = system_instruction_map(size)
        partials: list[str] = []
        for ch in chunks:
            piece = ch
            if len(piece) > self._map_chunk_max:
                piece = clip_head_tail(piece, self._map_chunk_max)
            messages = [
                {"role": "system", "content": sys_map},
                {"role": "user", "content": user_map_chunk(piece)},
            ]
            partials.append(self._adaptive_chat(messages, tag=f"summary-map-{len(partials)}"))

        reduce_user = user_reduce(partials, size)
        if len(reduce_user) > self._max_reduce_chars:
            logger.warning(
                "Reduce prompt clipped from %d to %d chars",
                len(reduce_user),
                self._max_reduce_chars,
            )
            reduce_user = clip_head_tail(reduce_user, self._max_reduce_chars)

        messages = [
            {"role": "system", "content": system_instruction_final(size)},
            {"role": "user", "content": reduce_user},
        ]
        out = self._adaptive_chat(messages, tag="summary-reduce")
        return SummaryResult(
            text=out,
            size=size,
            model=self._client.model,
            mode="map_reduce",
            source_chunks=len(chunks),
        )
