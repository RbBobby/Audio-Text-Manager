from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobCreateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    stages: dict[str, str]
    error: str | None
    created_at: str
    updated_at: str


class JobResultResponse(BaseModel):
    job_id: str
    transcript: str
    summary: str
    timings: dict[str, Any]
    model_info: dict[str, Any]


class JobTranscriptResponse(BaseModel):
    job_id: str
    transcript: str
    status: str
    stages: dict[str, str]


class JobListItem(BaseModel):
    id: str
    status: str
    asr_preset: str
    summary_size: str
    original_filename: str | None
    stages: dict[str, str]
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    limit: int
    offset: int


class JobRequeueBody(BaseModel):
    asr_model: str = Field(..., description="ASR preset: fast, medium, high")
    summary_size: str = Field(
        ...,
        description="gist | executive | meeting (legacy: short, medium, long)",
    )
    custom_prompt: str | None = Field(
        default=None,
        description="Optional; set to null to clear custom LLM instructions",
    )


class JobRequeueResponse(BaseModel):
    job_id: str
    status: str


class JobSummarizeOnlyBody(BaseModel):
    """Повторный саммари по уже сохранённому транскрипту (ASR не запускается)."""

    summary_size: str = Field(
        ...,
        description="gist | executive | meeting (legacy: short, medium, long)",
    )
    custom_prompt: str | None = Field(
        default=None,
        description="Опционально: свой промпт; иначе пресеты по summary_size",
    )


class JobSummarizeOnlyResponse(BaseModel):
    job_id: str
    status: str


class JobBulkDeleteBody(BaseModel):
    job_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="UUID задач для удаления (запись в БД и загруженный аудиофайл)",
    )


class JobBulkDeleteSkipped(BaseModel):
    id: str
    reason: str


class JobBulkDeleteResponse(BaseModel):
    deleted: list[str]
    skipped: list[JobBulkDeleteSkipped]
