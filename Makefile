.DEFAULT_GOAL := help

VENV ?= .venv
HOST ?= 127.0.0.1
PORT ?= 8000

ifeq ($(OS),Windows_NT)
  PYTHON ?= python
  PY := $(VENV)/Scripts/python.exe
else
  PYTHON ?= python3
  PY := $(VENV)/bin/python
endif

.PHONY: help install run dev test ollama-cpu ollama-metal

help:
	@echo "Audio Text Manager"
	@echo
	@echo "  make install       venv + зависимости (включая pytest)"
	@echo "  make run           сервер  http://$(HOST):$(PORT)/app/"
	@echo "  make dev           то же, с --reload"
	@echo "  make test          pytest"
	@echo "  make ollama-cpu    ollama serve без GPU (обход крашей Metal на Apple Silicon)"
	@echo
	@echo "Перед make run нужен ffmpeg в PATH и запущенный Ollama (ollama serve)."
	@echo "HOST/PORT: make run PORT=8001"
	@echo "Windows без GNU Make: make.bat install && make.bat run"

$(PY):
	$(PYTHON) -m venv $(VENV)

install: $(PY)
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev]"

run: $(PY)
	@$(PY) -c "import uvicorn" || $(MAKE) install
	$(PY) -m uvicorn backend.app.main:app --host $(HOST) --port $(PORT)

dev: $(PY)
	@$(PY) -c "import uvicorn" || $(MAKE) install
	$(PY) -m uvicorn backend.app.main:app --host $(HOST) --port $(PORT) --reload

test: $(PY)
	@$(PY) -c "import pytest" || $(MAKE) install
	$(PY) -m pytest

ifeq ($(OS),Windows_NT)
ollama-cpu ollama-metal:
	@echo "macOS-only. On Windows start Ollama from the Start menu or run: ollama serve"
else
ollama-cpu:
	bash scripts/ollama-serve-macos-cpu.sh

ollama-metal:
	bash scripts/ollama-serve-macos-metal-safe.sh
endif
