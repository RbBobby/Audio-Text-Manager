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
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
"""


def init_database(sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), timeout=60.0)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
