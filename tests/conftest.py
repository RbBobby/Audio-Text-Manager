from __future__ import annotations

import os
import shutil
import tempfile

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Isolated data dir before collection (so first import sees correct env)."""
    if os.environ.get("ATM_DATA_DIR"):
        config._atm_managed = None  # type: ignore[attr-defined]
        return
    d = tempfile.mkdtemp(prefix="atm_pytest_")
    os.environ["ATM_DATA_DIR"] = d
    os.environ.setdefault("ATM_MAX_AUDIO_DURATION_SEC", "0")
    os.environ.setdefault("ATM_LOG_LEVEL", "WARNING")
    config._atm_managed = d  # type: ignore[attr-defined]


def pytest_unconfigure(config: pytest.Config) -> None:
    d = getattr(config, "_atm_managed", None)
    if d:
        shutil.rmtree(d, ignore_errors=True)
        os.environ.pop("ATM_DATA_DIR", None)
