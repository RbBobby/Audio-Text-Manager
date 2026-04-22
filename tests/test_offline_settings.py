from __future__ import annotations

import os

import pytest

from backend.app.settings import Settings


def test_offline_sets_whisper_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATM_OFFLINE", "1")
    monkeypatch.delenv("ATM_WHISPER_LOCAL_ONLY", raising=False)
    s = Settings.from_env()
    assert s.offline_mode is True
    assert s.whisper_local_files_only is True
    assert s.ollama_trust_env is False


def test_whisper_local_only_without_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATM_OFFLINE", raising=False)
    monkeypatch.setenv("ATM_WHISPER_LOCAL_ONLY", "true")
    s = Settings.from_env()
    assert s.offline_mode is False
    assert s.whisper_local_files_only is True


def test_ollama_disable_trust_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATM_OFFLINE", raising=False)
    monkeypatch.setenv("ATM_OLLAMA_DISABLE_TRUST_ENV", "1")
    s = Settings.from_env()
    assert s.ollama_trust_env is False


def test_ollama_num_gpu_zero_when_cpu_brand_is_m5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATM_OLLAMA_ALLOW_METAL", raising=False)
    monkeypatch.delenv("ATM_OLLAMA_NUM_GPU", raising=False)
    monkeypatch.setattr(
        "backend.app.settings._darwin_cpu_brand", lambda: "Apple M5"
    )
    s = Settings.from_env()
    assert s.ollama_num_gpu == 0
    assert s.apple_m5_cpu is True


def test_ollama_num_gpu_none_when_allow_metal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATM_OLLAMA_ALLOW_METAL", "1")
    monkeypatch.delenv("ATM_OLLAMA_NUM_GPU", raising=False)
    monkeypatch.setattr(
        "backend.app.settings._darwin_cpu_brand", lambda: "Apple M5"
    )
    s = Settings.from_env()
    assert s.ollama_num_gpu is None


def test_ollama_num_gpu_env_overrides_m5_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATM_OLLAMA_ALLOW_METAL", raising=False)
    monkeypatch.setenv("ATM_OLLAMA_NUM_GPU", "99")
    monkeypatch.setattr(
        "backend.app.settings._darwin_cpu_brand", lambda: "Apple M5"
    )
    s = Settings.from_env()
    assert s.ollama_num_gpu == 99


def test_ollama_num_gpu_none_on_non_m5_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATM_OLLAMA_ALLOW_METAL", raising=False)
    monkeypatch.delenv("ATM_OLLAMA_NUM_GPU", raising=False)
    monkeypatch.setattr(
        "backend.app.settings._darwin_cpu_brand", lambda: "Apple M1 Pro"
    )
    s = Settings.from_env()
    assert s.ollama_num_gpu is None
    assert s.apple_m5_cpu is False


def test_ollama_homebrew_formula_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.settings.ollama_binary_looks_like_homebrew_formula",
        lambda: True,
    )
    s = Settings.from_env()
    assert s.ollama_homebrew_formula is True
