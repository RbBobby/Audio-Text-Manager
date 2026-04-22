from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  asr_preset TEXT NOT NULL,
  summary_size TEXT NOT NULL,
  original_filename TEXT,
  audio_path TEXT NOT NULL,
  error_message TEXT,
  transcript TEXT,
  summary TEXT,
  timings_json TEXT,
  stages_json TEXT NOT NULL,
  model_info_json TEXT,
  custom_prompt TEXT,
  summarize_only INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
"""


def _ensure_jobs_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(jobs)")
    cols = {row[1] for row in cur.fetchall()}
    if "custom_prompt" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN custom_prompt TEXT")
    if "summarize_only" not in cols:
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN summarize_only INTEGER NOT NULL DEFAULT 0"
        )


def init_database(sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), timeout=60.0)
    try:
        conn.executescript(_SCHEMA)
        _ensure_jobs_columns(conn)
        conn.commit()
    finally:
        conn.close()
