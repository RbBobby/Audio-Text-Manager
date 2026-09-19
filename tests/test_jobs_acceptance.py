from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.jobs import repository as repo
from backend.app.settings import Settings


@pytest.fixture
def tiny_audio(tmp_path: Path) -> Path:
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
            "sine=frequency=300:duration=0.2",
            str(out),
        ],
        check=True,
    )
    return out


def _fake_pipeline(job_id: str, settings: Settings) -> None:
    db = settings.sqlite_path
    row = repo.get_job(db, job_id)
    if not row or row["status"] != "processing":
        return
    st = {"upload": "done", "asr": "done", "summarize": "done"}
    repo.update_stages_and_optional(
        db,
        job_id,
        stages=st,
        status="done",
        transcript="hello acceptance",
        summary="summary " + row["summary_size"],
        timings={"asr_ms": 5, "summarize_ms": 7},
        model_info={
            "whisper_model": "small",
            "ollama_model": settings.ollama_model,
            "summary_size": row["summary_size"],
        },
    )


@pytest.mark.parametrize("summary_size", ("gist", "executive", "meeting"))
def test_e2e_job_done_and_result(
    monkeypatch: pytest.MonkeyPatch,
    tiny_audio: Path,
    summary_size: str,
) -> None:
    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", _fake_pipeline)
    from backend.app.main import app

    with TestClient(app) as client:
        with tiny_audio.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("test.wav", f, "audio/wav")},
                data={"asr_model": "fast", "summary_size": summary_size},
            )
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        deadline = time.time() + 15
        status = None
        last = None
        while time.time() < deadline:
            last = client.get(f"/jobs/{job_id}").json()
            status = last["status"]
            if status == "done":
                break
            time.sleep(0.08)
        assert status == "done", last

        res = client.get(f"/jobs/{job_id}/result")
        assert res.status_code == 200
        body = res.json()
        assert "hello acceptance" in body["transcript"]
        assert summary_size in body["summary"]
        assert body["timings"]["asr_ms"] == 5


@pytest.mark.parametrize("ext", (".wav", ".mp3", ".m4a"))
def test_three_audio_container_extensions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ext: str,
) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src = tmp_path / f"a{ext}"
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
            "sine=frequency=200:duration=0.15",
            str(src),
        ],
        check=True,
    )

    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", _fake_pipeline)
    from backend.app.main import app

    mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}[ext]
    with TestClient(app) as client:
        with src.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": (f"test{ext}", f, mime)},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        assert r.status_code == 200, r.text


def _write_mp4(path: Path, *, with_audio: bool) -> None:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=160x120:d=0.2",
    ]
    if with_audio:
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=200:duration=0.2",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-shortest",
            ]
        )
    else:
        cmd.extend(["-an", "-c:v", "mpeg4"])
    cmd.append(str(path))
    subprocess.run(cmd, check=True)


def test_accept_mp4_with_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src = tmp_path / "clip.mp4"
    _write_mp4(src, with_audio=True)

    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", _fake_pipeline)
    from backend.app.main import app

    with TestClient(app) as client:
        with src.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("clip.mp4", f, "video/mp4")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        st = client.get(f"/jobs/{job_id}")
        assert st.status_code == 200
        assert st.json()["status"] in ("queued", "processing", "done")
        from backend.app.main import app as loaded_app

        row = repo.get_job(loaded_app.state.settings.sqlite_path, job_id)
        audio = Path(row["audio_path"])
        assert audio.suffix.lower() == ".wav"
        assert audio.is_file()
        assert not audio.with_suffix(".mp4").is_file()


def test_reject_mp4_without_audio(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe not installed")
    src = tmp_path / "silent.mp4"
    _write_mp4(src, with_audio=False)
    from backend.app.main import app

    with TestClient(app) as client:
        with src.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("silent.mp4", f, "video/mp4")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
    assert r.status_code == 400
    assert "audio" in r.json()["detail"].lower()


def test_video_limit_does_not_block_small_audio(
    monkeypatch: pytest.MonkeyPatch,
    tiny_audio: Path,
) -> None:
    monkeypatch.setenv("ATM_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
    monkeypatch.setenv("ATM_MAX_VIDEO_UPLOAD_BYTES", "1")
    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", _fake_pipeline)
    from backend.app.main import app

    with TestClient(app) as client:
        with tiny_audio.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("ok.wav", f, "audio/wav")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        assert r.status_code == 200, r.text


def test_audio_over_limit_413_even_if_video_limit_is_huge(
    monkeypatch: pytest.MonkeyPatch,
    tiny_audio: Path,
) -> None:
    monkeypatch.setenv("ATM_MAX_UPLOAD_BYTES", "10")
    monkeypatch.setenv("ATM_MAX_VIDEO_UPLOAD_BYTES", str(50 * 1024 * 1024))
    from backend.app.main import app

    with TestClient(app) as client:
        with tiny_audio.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("big.wav", f, "audio/wav")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
    assert r.status_code == 413
    detail = r.json()["detail"].lower()
    assert "audio" in detail
    assert "atm_max_upload_bytes" in detail


def test_mp4_uses_video_upload_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    monkeypatch.setenv("ATM_MAX_UPLOAD_BYTES", "10")
    monkeypatch.setenv("ATM_MAX_VIDEO_UPLOAD_BYTES", str(50 * 1024 * 1024))
    src = tmp_path / "clip.mp4"
    _write_mp4(src, with_audio=True)
    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", _fake_pipeline)
    from backend.app.main import app

    with TestClient(app) as client:
        with src.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("clip.mp4", f, "video/mp4")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        assert r.status_code == 200, r.text


def test_result_409_while_processing(
    monkeypatch: pytest.MonkeyPatch,
    tiny_audio: Path,
) -> None:
    import backend.app.jobs.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline", lambda *a, **k: None)
    from backend.app.main import app

    with TestClient(app) as client:
        with tiny_audio.open("rb") as f:
            r = client.post(
                "/jobs",
                files={"audio_file": ("x.wav", f, "audio/wav")},
                data={"asr_model": "fast", "summary_size": "gist"},
            )
        job_id = r.json()["job_id"]
        deadline = time.time() + 10
        seen_processing = False
        while time.time() < deadline:
            st = client.get(f"/jobs/{job_id}").json()
            if st["status"] == "processing":
                seen_processing = True
                conflict = client.get(f"/jobs/{job_id}/result")
                assert conflict.status_code == 409
                break
            time.sleep(0.06)
        assert seen_processing, "expected job to enter processing state"


def test_reject_bad_extension() -> None:
    from backend.app.main import app

    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            files={"audio_file": ("x.txt", b"abc", "text/plain")},
            data={"asr_model": "fast", "summary_size": "gist"},
        )
    assert r.status_code == 400


def test_logging_config_smoke() -> None:
    from backend.app.logging_config import setup_logging

    setup_logging("DEBUG")
    setup_logging("INFO")
