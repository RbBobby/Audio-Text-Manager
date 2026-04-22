from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path), timeout=60.0)


def insert_job(
    sqlite_path: Path,
    *,
    job_id: str,
    asr_preset: str,
    summary_size: str,
    original_filename: str,
    audio_path: str,
    stages: dict[str, str],
    custom_prompt: str | None = None,
) -> None:
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            """
            INSERT INTO jobs (
              id, status, asr_preset, summary_size, original_filename,
              audio_path, stages_json, custom_prompt, summarize_only,
              created_at, updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))
            """,
            (
                job_id,
                asr_preset,
                summary_size,
                original_filename,
                audio_path,
                json.dumps(stages),
                custom_prompt,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_job(sqlite_path: Path, job_id: str) -> dict[str, Any] | None:
    conn = _connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}
    finally:
        conn.close()


def claim_next_queued(sqlite_path: Path) -> str | None:
    """Atomically pick the oldest queued job and mark it processing.

    Jobs with summarize_only=1 skip ASR: only Ollama runs on existing transcript.
    Such jobs are claimed before full jobs (same created order within bucket).
    """
    conn = _connect(sqlite_path)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            SELECT id, summarize_only FROM jobs
            WHERE status = 'queued'
            ORDER BY summarize_only DESC, datetime(created_at) ASC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        job_id = row[0]
        summarize_only = int(row[1] or 0)
        if summarize_only:
            stages = {"upload": "done", "asr": "done", "summarize": "processing"}
        else:
            stages = {"upload": "done", "asr": "processing", "summarize": "pending"}
        conn.execute(
            """
            UPDATE jobs SET
              status = 'processing',
              stages_json = ?,
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (json.dumps(stages), job_id),
        )
        conn.execute("COMMIT")
        return job_id
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    finally:
        conn.close()


def list_jobs(
    sqlite_path: Path,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = _connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, status, asr_preset, summary_size, original_filename,
                   audio_path, stages_json, created_at, updated_at
            FROM jobs
            ORDER BY datetime(updated_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "status": r["status"],
                "asr_preset": r["asr_preset"],
                "summary_size": r["summary_size"],
                "original_filename": r["original_filename"],
                "audio_path": r["audio_path"],
                "stages": json.loads(r["stages_json"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def requeue_job(
    sqlite_path: Path,
    job_id: str,
    *,
    asr_preset: str,
    summary_size: str,
    custom_prompt: str | None,
) -> None:
    row = get_job(sqlite_path, job_id)
    if row is None:
        raise LookupError("job not found")
    if row["status"] == "processing":
        raise RuntimeError("job is processing")
    audio = Path(row["audio_path"])
    if not audio.is_file():
        raise FileNotFoundError("audio file missing")
    stages = {"upload": "done", "asr": "pending", "summarize": "pending"}
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            """
            UPDATE jobs SET
              asr_preset = ?,
              summary_size = ?,
              custom_prompt = ?,
              status = 'queued',
              summarize_only = 0,
              transcript = NULL,
              summary = NULL,
              timings_json = NULL,
              model_info_json = NULL,
              error_message = NULL,
              stages_json = ?,
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (asr_preset, summary_size, custom_prompt, json.dumps(stages), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def queue_summarize_only(
    sqlite_path: Path,
    job_id: str,
    *,
    summary_size: str,
    custom_prompt: str | None,
) -> None:
    """Re-run LLM on existing transcript without ASR. Sets status queued + summarize_only=1."""
    row = get_job(sqlite_path, job_id)
    if row is None:
        raise LookupError("job not found")
    if row["status"] == "processing":
        raise RuntimeError("job is processing")
    text = (row.get("transcript") or "").strip()
    if not text:
        raise ValueError("no transcript to summarize")
    stages = {"upload": "done", "asr": "done", "summarize": "pending"}
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            """
            UPDATE jobs SET
              summary_size = ?,
              custom_prompt = ?,
              summarize_only = 1,
              status = 'queued',
              summary = NULL,
              timings_json = NULL,
              model_info_json = NULL,
              error_message = NULL,
              stages_json = ?,
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (summary_size, custom_prompt, json.dumps(stages), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_summarize_only_flag(sqlite_path: Path, job_id: str) -> None:
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            "UPDATE jobs SET summarize_only = 0 WHERE id = ?",
            (job_id,),
        )
        conn.commit()
    finally:
        conn.close()


def update_stages_and_optional(
    sqlite_path: Path,
    job_id: str,
    *,
    stages: dict[str, str],
    status: str | None = None,
    transcript: str | None = None,
    summary: str | None = None,
    timings: dict[str, Any] | None = None,
    model_info: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    conn = _connect(sqlite_path)
    try:
        fields = ["stages_json = ?", "updated_at = datetime('now')"]
        values: list[Any] = [json.dumps(stages)]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if transcript is not None:
            fields.append("transcript = ?")
            values.append(transcript)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if timings is not None:
            fields.append("timings_json = ?")
            values.append(json.dumps(timings))
        if model_info is not None:
            fields.append("model_info_json = ?")
            values.append(json.dumps(model_info))
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        values.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
        conn.execute(sql, values)
        conn.commit()
    finally:
        conn.close()
