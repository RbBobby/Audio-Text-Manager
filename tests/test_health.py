from __future__ import annotations

from backend.app.main import app
from fastapi.testclient import TestClient


def test_health() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
