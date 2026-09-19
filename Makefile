.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
HOST ?= 127.0.0.1
PORT ?= 8000

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
	@echo "HOST/PORT можно переопределить: make run PORT=8001"

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

install: $(BIN)/python
	$(BIN)/python -m pip install -U pip
	$(BIN)/pip install -e ".[dev]"

run: $(BIN)/python
	@$(BIN)/python -c "import uvicorn" >/dev/null 2>&1 || $(MAKE) install
	$(BIN)/python -m uvicorn backend.app.main:app --host $(HOST) --port $(PORT)

dev: $(BIN)/python
	@$(BIN)/python -c "import uvicorn" >/dev/null 2>&1 || $(MAKE) install
	$(BIN)/python -m uvicorn backend.app.main:app --host $(HOST) --port $(PORT) --reload

test: $(BIN)/python
	@$(BIN)/python -c "import pytest" >/dev/null 2>&1 || $(MAKE) install
	$(BIN)/python -m pytest

ollama-cpu:
	bash scripts/ollama-serve-macos-cpu.sh

ollama-metal:
	bash scripts/ollama-serve-macos-metal-safe.sh
