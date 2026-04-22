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
) -> None:
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            """
            INSERT INTO jobs (
              id, status, asr_preset, summary_size, original_filename,
              audio_path, stages_json, created_at, updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                job_id,
                asr_preset,
                summary_size,
                original_filename,
                audio_path,
                json.dumps(stages),
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
    """Atomically pick the oldest queued job and mark it processing."""
    conn = _connect(sqlite_path)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            SELECT id FROM jobs
            WHERE status = 'queued'
            ORDER BY datetime(created_at) ASC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        job_id = row[0]
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
