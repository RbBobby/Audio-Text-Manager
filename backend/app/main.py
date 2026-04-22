from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.jobs.database import init_database
from backend.app.jobs.routes import router as jobs_router
from backend.app.jobs.worker import start_worker
from backend.app.logging_config import setup_logging
from backend.app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    settings.ensure_dirs()
    init_database(settings.sqlite_path)
    app.state.settings = settings
    worker = start_worker(settings)
    app.state.worker = worker
    yield
    worker.stop.set()
    worker.thread.join(timeout=120.0)


app = FastAPI(
    title="Audio Text Manager API",
    version="0.1.0",
    description="Offline-first ASR and summarization backend.",
    lifespan=lifespan,
)

app.include_router(jobs_router)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="app",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    out: dict[str, str] = {
        "service": "audio-text-manager",
        "docs": "/docs",
    }
    if _FRONTEND_DIR.is_dir():
        out["ui"] = "/app/"
    return out
