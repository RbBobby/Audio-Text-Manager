# Audio Text Manager

Локальный сервис: загрузка аудио → **распознавание речи** ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) → **саммари** через [Ollama](https://ollama.com/) (`/api/chat`). API на **FastAPI**, фоновые джобы — воркер в том же процессе.

## Требования

| Компонент | Зачем |
|-----------|--------|
| **Python 3.10+** | бэкенд |
| **ffmpeg** (+ **ffprobe**) | нормализация аудио перед Whisper |
| **Ollama** | LLM для саммари (локально, `http://127.0.0.1:11434` по умолчанию) |

Опционально: **CUDA** — если ставите `ctranslate2` с GPU; иначе faster-whisper использует CPU (на Apple Silicon обычно через Metal, если сборка это поддерживает).

---

## Сборка с нуля

### 1. Клонирование и виртуальное окружение

```bash
git clone <URL-репозитория> audio-text-manager
cd audio-text-manager

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install -e ".[dev]"     # без dev: pip install -e .
```

Установка в режиме `-e` нужна, чтобы импорт `backend.app` работал из корня проекта.

### 2. ffmpeg

- **macOS (Homebrew):** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- Проверка: `ffmpeg -version` и `ffprobe -version`

### 3. Ollama

1. Установите Ollama: [ollama.com/download](https://ollama.com/download) или `brew install --cask ollama`.
2. Запустите сервер (отдельный терминал):

   ```bash
   ollama serve
   ```

3. Подтяните модель под умолчание приложения (или смените имя через `ATM_OLLAMA_MODEL`):

   ```bash
   ollama pull qwen2.5:14b-instruct-q4_K_M
   ```

   Для слабой машины возьмите меньшую модель, например `qwen2.5:7b-instruct-q4_K_M`, и задайте:

   ```bash
   export ATM_OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
   ```

**Apple M5 и ошибки Metal (HTTP 500, `llama runner process has terminated`):** это известная проблема Ollama + macOS. Попробуйте запуск сервера с:

```bash
GGML_METAL_TENSOR_DISABLE=1 ollama serve
```

Подробнее: [ollama/ollama#14432](https://github.com/ollama/ollama/issues/14432).

### 4. Whisper (faster-whisper)

Модели **Systran/faster-whisper** (CTranslate2) качаются при **первом** запуске транскрипции в кэш Hugging Face (или в каталог из `ATM_WHISPER_DOWNLOAD_ROOT`).

Пресеты ASR в API:

| `asr_model` (форма) | Модель Whisper |
|---------------------|------------------|
| `fast` | `small` |
| `medium` | `medium` |
| `high` | `large-v3` |

Полностью офлайн (без скачивания из сети):

```bash
export ATM_OFFLINE=1
# или только Whisper без полного офлайна:
export ATM_WHISPER_LOCAL_ONLY=1
```

Тогда нужны уже скачанные веса в кэше / в `ATM_WHISPER_DOWNLOAD_ROOT`.

### 5. Запуск приложения

Из **корня репозитория** (с активированным venv):

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

- **API:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health:** `GET /health`
- **UI:** если есть каталог `frontend/`, откройте [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/)

Данные по умолчанию: каталог `data/` (SQLite `data/app.db`, загрузки `data/uploads/`). Пути переопределяются переменными окружения (см. `configs/app.example.yaml` и `backend/app/settings.py`).

### 6. Проверка

```bash
pytest
```

---

## Полезные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `ATM_DATA_DIR` | корень данных (по умолчанию `data`) |
| `ATM_OLLAMA_BASE_URL` | URL Ollama (по умолчанию `http://127.0.0.1:11434`) |
| `ATM_OLLAMA_MODEL` | тег модели в Ollama |
| `ATM_OFFLINE` | офлайн: Whisper без скачивания, Ollama `trust_env=false` |
| `ATM_WHISPER_DOWNLOAD_ROOT` | каталог кэша CTranslate2 |
| `ATM_OLLAMA_NUM_CTX`, `ATM_OLLAMA_NUM_PREDICT` | контекст и лимит ответа для саммари |
| `ATM_LOG_LEVEL` | `DEBUG`, `INFO`, … |

Полный список и комментарии — в `configs/app.example.yaml`.

---

## API в двух словах

- `POST /jobs` — форма: `audio_file`, `asr_model` (`fast` \| `medium` \| `high`), `summary_size` (`short` \| `medium` \| `long`).
- `GET /jobs/{id}` — статус и стадии.
- `GET /jobs/{id}/result` — транскрипт и саммари, когда джоб `done`.

---

## Структура репозитория

```
backend/app/     # FastAPI, ASR, саммари, джобы, настройки
frontend/        # статическая оболочка UI (если есть)
configs/         # пример конфигурации (основной источник правды для env — settings)
tests/
```

Лицензия и версия — в `pyproject.toml`.
