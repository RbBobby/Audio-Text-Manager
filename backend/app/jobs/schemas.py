from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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
