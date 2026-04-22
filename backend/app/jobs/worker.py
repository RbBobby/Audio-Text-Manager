from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from backend.app.settings import Settings

from . import repository as repo
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


@dataclass
class WorkerHandle:
    thread: threading.Thread
    stop: threading.Event


def _loop(stop: threading.Event, settings: Settings) -> None:
    while not stop.is_set():
        job_id = repo.claim_next_queued(settings.sqlite_path)
        if job_id:
            try:
                logger.info("Processing job %s", job_id)
                run_pipeline(job_id, settings)
            except Exception:
                logger.exception("Unhandled error in pipeline for job %s", job_id)
        else:
            stop.wait(0.35)


def start_worker(settings: Settings) -> WorkerHandle:
    stop = threading.Event()
    th = threading.Thread(
        target=_loop,
        args=(stop, settings),
        daemon=True,
        name="atm-job-worker",
    )
    th.start()
    return WorkerHandle(thread=th, stop=stop)
