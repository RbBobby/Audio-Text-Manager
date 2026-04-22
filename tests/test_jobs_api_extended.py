from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.jobs import repository as repo


@pytest.fixture
def tiny_wav(tmp_path: Path) -> Path:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "clip.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=0.15",
            str(out),
        ],
        check=True,
    )
    return out


@pytest.fixture
def client_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ATM_SQLITE_PATH", str(tmp_path / "jobs.sqlite"))
    monkeypatch.setenv("ATM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "backend.app.jobs.worker.repo.claim_next_queued",
        lambda *_args, **_kwargs: None,
    )
    from backend.app.main import app

    with TestClient(app) as client:
        yield client, tmp_path


def test_list_jobs_empty(client_isolated: tuple[TestClient, Path]) -> None:
    client, _ = client_isolated
    r = client.get("/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["jobs"] == []
    assert body["limit"] == 50


def test_transcript_425_before_ready(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, _ = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    tr = client.get(f"/jobs/{job_id}/transcript")
    assert tr.status_code == 425


def test_transcript_200_after_manual_write(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    repo.update_stages_and_optional(
        db,
        job_id,
        stages={"upload": "done", "asr": "done", "summarize": "processing"},
        status="processing",
        transcript="hello transcript",
    )
    tr = client.get(f"/jobs/{job_id}/transcript")
    assert tr.status_code == 200
    body = tr.json()
    assert body["transcript"] == "hello transcript"
    assert body["job_id"] == job_id
    assert body["stages"]["asr"] == "done"


def test_transcript_404_unknown_job(client_isolated: tuple[TestClient, Path]) -> None:
    client, _ = client_isolated
    r = client.get("/jobs/00000000-0000-0000-0000-000000000000/transcript")
    assert r.status_code == 404


def test_transcript_409_on_error_without_transcript(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    repo.update_stages_and_optional(
        db,
        job_id,
        stages={"upload": "done", "asr": "error", "summarize": "pending"},
        status="error",
        error_message="ASR failed",
    )
    tr = client.get(f"/jobs/{job_id}/transcript")
    assert tr.status_code == 409


def test_requeue_success(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    row = repo.get_job(Path(tmp / "jobs.sqlite"), job_id)
    assert row is not None
    audio = Path(row["audio_path"])
    assert audio.is_file()
    repo.update_stages_and_optional(
        Path(tmp / "jobs.sqlite"),
        job_id,
        stages={"upload": "done", "asr": "done", "summarize": "done"},
        status="done",
        transcript="t",
        summary="s",
        timings={"asr_ms": 1, "summarize_ms": 2},
        model_info={"x": 1},
    )
    rq = client.post(
        f"/jobs/{job_id}/requeue",
        json={"asr_model": "medium", "summary_size": "meeting"},
    )
    assert rq.status_code == 200, rq.text
    assert rq.json() == {"job_id": job_id, "status": "queued"}
    row2 = repo.get_job(Path(tmp / "jobs.sqlite"), job_id)
    assert row2["status"] == "queued"
    assert row2["asr_preset"] == "medium"
    assert row2["summary_size"] == "meeting"
    assert row2["transcript"] is None


def test_requeue_410_missing_audio(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    row = repo.get_job(Path(tmp / "jobs.sqlite"), job_id)
    Path(row["audio_path"]).unlink()
    repo.update_stages_and_optional(
        Path(tmp / "jobs.sqlite"),
        job_id,
        stages={"upload": "done", "asr": "done", "summarize": "done"},
        status="done",
        transcript="t",
        summary="s",
    )
    rq = client.post(
        f"/jobs/{job_id}/requeue",
        json={"asr_model": "fast", "summary_size": "gist"},
    )
    assert rq.status_code == 410


def test_requeue_409_while_processing(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    repo.update_stages_and_optional(
        Path(tmp / "jobs.sqlite"),
        job_id,
        stages={"upload": "done", "asr": "processing", "summarize": "pending"},
        status="processing",
    )
    rq = client.post(
        f"/jobs/{job_id}/requeue",
        json={"asr_model": "fast", "summary_size": "gist"},
    )
    assert rq.status_code == 409


def test_list_jobs_order(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    ids = []
    for i in range(2):
        with tiny_wav.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": (f"{i}.wav", f, "audio/wav")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        ids.append(r.json()["job_id"])
    lst = client.get("/jobs?limit=10&offset=0")
    assert lst.status_code == 200
    jobs = lst.json()["jobs"]
    assert len(jobs) == 2
    assert {jobs[0]["id"], jobs[1]["id"]} == set(ids)


def test_summarize_only_queues_without_asr(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    repo.update_stages_and_optional(
        db,
        job_id,
        stages={"upload": "done", "asr": "done", "summarize": "done"},
        status="done",
        transcript="only text",
        summary="old",
        timings={"asr_ms": 100, "summarize_ms": 50},
        model_info={"whisper_model": "small"},
    )
    rq = client.post(
        f"/jobs/{job_id}/summarize",
        json={"summary_size": "meeting", "custom_prompt": "Bullet points"},
    )
    assert rq.status_code == 200, rq.text
    assert rq.json() == {"job_id": job_id, "status": "queued"}
    row = repo.get_job(db, job_id)
    assert row["status"] == "queued"
    assert int(row.get("summarize_only") or 0) == 1
    assert row["summary_size"] == "meeting"
    assert row["custom_prompt"] == "Bullet points"
    assert row["transcript"] == "only text"
    assert row["summary"] is None


def test_summarize_only_400_without_transcript(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    repo.update_stages_and_optional(
        db,
        job_id,
        stages={"upload": "done", "asr": "done", "summarize": "done"},
        status="done",
        transcript="",
        summary="x",
    )
    rq = client.post(
        f"/jobs/{job_id}/summarize",
        json={"summary_size": "gist"},
    )
    assert rq.status_code == 400


def test_create_job_with_custom_prompt_form(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={
                "asr_model": "fast",
                "summary_size": "gist",
                "custom_prompt": "  List key dates  ",
            },
        )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    row = repo.get_job(Path(tmp / "jobs.sqlite"), job_id)
    assert row["custom_prompt"] == "List key dates"


def test_bulk_delete_removes_row_and_audio_file(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    row = repo.get_job(db, job_id)
    audio = Path(row["audio_path"])
    assert audio.is_file()
    rd = client.post("/jobs/bulk-delete", json={"job_ids": [job_id]})
    assert rd.status_code == 200
    assert rd.json() == {"deleted": [job_id], "skipped": []}
    assert repo.get_job(db, job_id) is None
    assert not audio.is_file()


def test_bulk_delete_skips_processing(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, tmp = client_isolated
    with tiny_wav.open("rb") as f:
        r = client.post(
            "/jobs",
            files={"audio_file": ("a.wav", f, "audio/wav")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    job_id = r.json()["job_id"]
    db = Path(tmp / "jobs.sqlite")
    repo.update_stages_and_optional(
        db,
        job_id,
        stages={"upload": "done", "asr": "processing", "summarize": "pending"},
        status="processing",
    )
    rd = client.post("/jobs/bulk-delete", json={"job_ids": [job_id]})
    assert rd.status_code == 200
    body = rd.json()
    assert body["deleted"] == []
    assert body["skipped"] == [{"id": job_id, "reason": "processing"}]
    assert repo.get_job(db, job_id) is not None


def test_bulk_delete_not_found_is_skipped(
    client_isolated: tuple[TestClient, Path], tiny_wav: Path
) -> None:
    client, _ = client_isolated
    rd = client.post(
        "/jobs/bulk-delete",
        json={"job_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert rd.status_code == 200
    assert rd.json()["deleted"] == []
    assert rd.json()["skipped"][0]["reason"] == "not_found"
