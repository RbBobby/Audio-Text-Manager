from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.app.asr import parse_asr_preset
from backend.app.media_probe import audio_duration_seconds
from backend.app.settings import Settings
from backend.app.summary import parse_summary_size

from . import repository as repo
from .schemas import JobCreateResponse, JobResultResponse, JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

ALLOWED_AUDIO_EXT = frozenset({".wav", ".mp3", ".m4a", ".flac"})


def _row_to_status(row: dict) -> JobStatusResponse:
    return JobStatusResponse(
        id=row["id"],
        status=row["status"],
        stages=json.loads(row["stages_json"]),
        error=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("", response_model=JobCreateResponse)
async def create_job(
    request: Request,
    asr_model: str = Form(),
    summary_size: str = Form(),
    audio_file: UploadFile = File(),
) -> JobCreateResponse:
    settings: Settings = request.app.state.settings
    try:
        preset = parse_asr_preset(asr_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        size = parse_summary_size(summary_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    raw_name = audio_file.filename or "upload"
    if ".." in raw_name or raw_name.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    safe_name = Path(raw_name).name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported extension {ext!r}; allowed: {sorted(ALLOWED_AUDIO_EXT)}",
        )

    job_id = str(uuid.uuid4())
    dest = settings.uploads_dir / f"{job_id}{ext}"

    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await audio_file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise

    if settings.max_audio_duration_sec > 0:
        duration = audio_duration_seconds(dest)
        if duration is not None and duration > settings.max_audio_duration_sec:
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Audio too long: {duration:.1f}s exceeds limit "
                    f"{settings.max_audio_duration_sec}s"
                ),
            )
        if duration is None:
            logger.warning(
                "Could not probe duration for upload (ffprobe missing or error); "
                "skipping max_audio_duration_sec check"
            )

    audio_abs = str(dest.resolve())
    stages = {"upload": "done", "asr": "pending", "summarize": "pending"}
    try:
        repo.insert_job(
            settings.sqlite_path,
            job_id=job_id,
            asr_preset=preset,
            summary_size=size,
            original_filename=safe_name,
            audio_path=audio_abs,
            stages=stages,
        )
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    logger.info(
        "Job %s queued preset=%s summary=%s file=%s",
        job_id,
        preset,
        size,
        safe_name,
    )
    return JobCreateResponse(job_id=job_id)


@router.get("/{job_id}/result", response_model=JobResultResponse)
def get_job_result(request: Request, job_id: str) -> JobResultResponse:
    settings: Settings = request.app.state.settings
    row = repo.get_job(settings.sqlite_path, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail={"message": "Job not completed", "status": row["status"]},
        )
    timings = json.loads(row["timings_json"]) if row.get("timings_json") else {}
    model_info = (
        json.loads(row["model_info_json"]) if row.get("model_info_json") else {}
    )
    return JobResultResponse(
        job_id=row["id"],
        transcript=row["transcript"] or "",
        summary=row["summary"] or "",
        timings=timings,
        model_info=model_info,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(request: Request, job_id: str) -> JobStatusResponse:
    settings: Settings = request.app.state.settings
    row = repo.get_job(settings.sqlite_path, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_status(row)
