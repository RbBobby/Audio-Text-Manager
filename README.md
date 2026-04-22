# Audio Text Manager

Локальный сервис: загрузка аудио → **распознавание речи** ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) → **саммари** через [Ollama](https://ollama.com/) (`/api/chat`). API на **FastAPI**, фоновые джобы — воркер в том же процессе.

## Требования

| Компонент | Зачем |
|-----------|--------|
| **Python 3.10+** | бэкенд и тесты |
| **ffmpeg** (+ **ffprobe** в составе ffmpeg) | нормализация аудио перед Whisper |
| **Ollama** | LLM для саммари (локально, `http://127.0.0.1:11434` по умолчанию) |
| **Интернет** (первый запуск) | скачивание весов Whisper и модели Ollama |

Опционально: **CUDA** (Windows/Linux) — если сборка `ctranslate2` с GPU; иначе faster-whisper на CPU (на Apple Silicon часто через Metal, если поддерживается сборкой).

---

## Whisper и faster-whisper

**Whisper** в этом проекте — модель **распознавания речи** в архитектуре [OpenAI Whisper](https://github.com/openai/whisper). Она **не** вызывается «как в оригинальной статье» через чистый PyTorch в рантайме джоба: для инференса используется **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** на движке **[CTranslate2](https://github.com/OpenNMT/CTranslate2)** (ускорение на CPU и при наличии — на GPU).

| Что | Где в проекте / как задаётся |
|-----|------------------------------|
| Зависимость | `faster-whisper` в `pyproject.toml`; ставится вместе с `pip install -e .` |
| Нормализация аудио перед ASR | **ffmpeg** (обязателен в `PATH`) — см. `backend/app/asr/ffmpeg_normalize.py` |
| Пресеты скорости/качества | `backend/app/asr/presets.py` → в API поле `asr_model`: `fast` / `medium` / `high` |
| Соответствие чекпоинтам Systran | `fast` → `small`, `medium` → `medium`, `high` → `large-v3` |
| Кэш весов и офлайн | Переменные `ATM_WHISPER_DOWNLOAD_ROOT`, `ATM_WHISPER_LOCAL_ONLY`, `ATM_OFFLINE` (см. ниже и `configs/app.example.yaml`) |

**Первый запуск транскрибации:** веса модели **скачиваются автоматически** (как правило в кэш Hugging Face в домашнем каталоге пользователя, если не задан `ATM_WHISPER_DOWNLOAD_ROOT`). Нужен доступ в интернет, если не включён офлайн-режим.

**Ориентир по диску под веса Whisper:** от порядка **~1 GB** (`small`) до **нескольких GB** (`large-v3`), плюс отдельно место под модель **Ollama** для саммари.

**Офлайн только для Whisper:** `ATM_WHISPER_LOCAL_ONLY=1` — без загрузок из сети; веса должны уже быть в кэше или в `ATM_WHISPER_DOWNLOAD_ROOT`. Полный офлайн приложения: `ATM_OFFLINE=1` (также влияет на Ollama, см. `settings.py`).

---

## Установка с нуля

Общий порядок: **Python → зависимости проекта** (в т.ч. **faster-whisper / Whisper** через `pip`) **→ ffmpeg → Ollama → модель Ollama → запуск сервера**. Каталог репозитория в примерах: `audio-text-manager`.

### Шаг 0. Клонирование и виртуальное окружение (все ОС)

```bash
git clone https://github.com/RbBobby/Audio-Text-Manager.git
cd audio-text-manager

python3 -m venv .venv
```

Активация venv:

| ОС | Команда |
|----|---------|
| **macOS / Linux** | `source .venv/bin/activate` |
| **Windows (cmd)** | `.venv\Scripts\activate.bat` |
| **Windows (PowerShell)** | `.\.venv\Scripts\Activate.ps1` |

Если PowerShell ругается на политику выполнения: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (один раз для пользователя).

Установка пакета (из корня репозитория, venv активирован):

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

Флаг `-e` (editable) нужен, чтобы импорт `backend.app` работал из корня проекта. Без тестов: `pip install -e .`

На этом шаге в виртуальное окружение попадает пакет **`faster-whisper`** (движок **Whisper** для транскрибации в проекте). Отдельной команды вида `brew install whisper` для него нет — только `pip` и зависимости из `pyproject.toml`.

---

### Установка на macOS

1. **Python 3.10+**  
   - С [python.org](https://www.python.org/downloads/macos/) или через Homebrew: `brew install python@3.12`  
   - Проверка: `python3 --version`

2. **ffmpeg**  
   ```bash
   brew install ffmpeg
   ```  
   Проверка: `ffmpeg -version` и `ffprobe -version`

3. **Whisper (faster-whisper)** — транскрибация  
   - Библиотека **уже установлена** на шаге 0 вместе с проектом (`pip install -e .` → зависимость `faster-whisper`). Это не отдельный продукт «Whisper.app», а Python-пакет поверх **CTranslate2**.  
   - Для работы ASR **обязателен ffmpeg** (п. 2): без него нормализация аудио перед Whisper не выполнится.  
   - **Веса** моделей Whisper (small / medium / large-v3 по пресету `asr_model`) при **первом** запуске распознавания скачиваются автоматически — нужен интернет; подробности и офлайн — в разделе [«Whisper и faster-whisper»](#whisper-и-faster-whisper).  
   - Опционально задайте `ATM_WHISPER_DOWNLOAD_ROOT`, если кэш весов должен лежать не в домашнем каталоге по умолчанию.  
   - Проверка импорта (из корня репозитория, **venv активирован**):  
     ```bash
     python -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"
     ```

4. **Ollama**  
   - Установка: [ollama.com/download](https://ollama.com/download) (macOS) или `brew install --cask ollama`  
   - Запуск API (отдельное окно терминала):  
     ```bash
     ollama serve
     ```  
   - Модель по умолчанию в примере конфига — `qwen2.5:14b-instruct-q4_K_M` (нужен запас RAM/VRAM):  
     ```bash
     ollama pull qwen2.5:14b-instruct-q4_K_M
     ```  
   - Слабее машина — меньшая модель и переменная окружения перед `uvicorn`:  
     ```bash
     export ATM_OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
     ```

5. **Apple Silicon и падения Ollama / Metal (HTTP 500, `llama runner process has terminated`)**  
   Запуск сервера с отключением проблемного пути Metal:  
   ```bash
   GGML_METAL_TENSOR_DISABLE=1 ollama serve
   ```  
   Подробнее: [ollama/ollama#14432](https://github.com/ollama/ollama/issues/14432).

6. **Запуск приложения** (корень репозитория, venv активирован, Ollama уже слушает порт):  
   ```bash
   uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

7. **Проверка в браузере**  
   - API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
   - UI: [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/) (если есть каталог `frontend/`)

8. **Тесты (опционально)**  
   ```bash
   pytest
   ```

---

### Установка на Windows

1. **Python 3.10+**  
   - Установщик с [python.org](https://www.python.org/downloads/windows/) — **включите «Add python.exe to PATH»**  
   - Либо: `winget install Python.Python.3.12`  
   - Закройте и снова откройте терминал после установки. Проверка: `python --version`

2. **Виртуальное окружение и pip**  
   В **cmd** или **PowerShell** из каталога репозитория:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate.bat
   python -m pip install -U pip
   pip install -e ".[dev]"
   ```

   В PowerShell активация: `.\.venv\Scripts\Activate.ps1`

3. **ffmpeg** (обязательно в `PATH`, вместе с `ffprobe`)  
   Один из вариантов:  
   - [winget](https://winget.run/pkg/Gyan.FFmpeg): `winget install Gyan.FFmpeg`  
   - [Chocolatey](https://chocolatey.org/): `choco install ffmpeg`  
   - [Scoop](https://scoop.sh/): `scoop install ffmpeg`  
   Новый терминал → `ffmpeg -version` и `ffprobe -version`

4. **Whisper (faster-whisper)** — транскрибация  
   - Устанавливается **вместе с проектом** на шаге 2 (`pip install -e .` → `faster-whisper`). Отдельного установщика Whisper для ASR не требуется.  
   - Нужны **ffmpeg** в PATH (шаг 3) и при первом распознавании — **интернет** для загрузки весов (или заранее подготовленный кэш / `ATM_WHISPER_DOWNLOAD_ROOT`, см. [раздел про Whisper](#whisper-и-faster-whisper)).  
   - Проверка (venv активирован):  
     ```bat
     python -c "from faster_whisper import WhisperModel; print('faster-whisper OK')"
     ```

5. **Ollama**  
   - Скачайте установщик: [ollama.com/download/windows](https://ollama.com/download/windows)  
   - После установки Ollama обычно поднимает сервис в фоне; при необходимости запустите **Ollama** из меню Пуск или проверьте [документацию](https://github.com/ollama/ollama/blob/main/docs/windows.md).  
   - В **отдельном** окне `cmd`/`PowerShell` можно явно выполнить: `ollama serve`  
   - Подтяните модель:  
     ```bat
     ollama pull qwen2.5:14b-instruct-q4_K_M
     ```  
   - Другая модель (перед запуском uvicorn в том же окне):  
     ```bat
     set ATM_OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
     ```  
     В PowerShell: `$env:ATM_OLLAMA_MODEL="qwen2.5:7b-instruct-q4_K_M"`

6. **Запуск приложения** (из корня репозитория, venv активирован):

   ```bat
   uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

7. **Проверка**  
   - [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
   - [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/)

8. **Тесты**  
   ```bat
   pytest
   ```  
   Нужен **ffmpeg** в PATH (часть тестов генерирует wav через lavfi).

Если на «чистом» Windows возникают проблемы со сборкой **faster-whisper** / CTranslate2, имеет смысл поставить [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) или использовать **WSL2** (Ubuntu в WSL) и следовать шагам как для Linux: `sudo apt install ffmpeg`, тот же venv и `pip install -e ".[dev]"`.

---

### Linux (кратко)

```bash
sudo apt update && sudo apt install -y ffmpeg python3 python3-venv
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -e ".[dev]"
# Whisper (faster-whisper) уже в venv; проверка: python -c "from faster_whisper import WhisperModel; print('OK')"
# Ollama: см. https://ollama.com/download/linux
ollama pull qwen2.5:14b-instruct-q4_K_M
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

---

### Офлайн и переменные для Whisper (напоминание)

Полный офлайн и только Whisper — см. раздел **«Whisper и faster-whisper»** выше. Примеры:

```bash
export ATM_OFFLINE=1          # macOS / Linux
# Windows cmd:   set ATM_OFFLINE=1
# PowerShell:    $env:ATM_OFFLINE="1"
```

Только без скачивания весов Whisper: `ATM_WHISPER_LOCAL_ONLY=1` (веса уже в кэше или в `ATM_WHISPER_DOWNLOAD_ROOT`).

---

### Где лежат данные

По умолчанию создаётся каталог **`data/`**: SQLite `data/app.db`, загрузки `data/uploads/`. Пути и лимиты задаются **переменными окружения** (`ATM_DATA_DIR`, `ATM_SQLITE_PATH`, `ATM_UPLOADS_DIR` и др.); полный перечень с пояснениями — в `configs/app.example.yaml` (файл служит шпаргалкой; приложение читает в первую очередь **env**, см. `backend/app/settings.py`).

---

## Полезные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `ATM_DATA_DIR` | корень данных (по умолчанию `data`) |
| `ATM_SQLITE_PATH` | путь к SQLite джобов (по умолчанию `$ATM_DATA_DIR/app.db`) |
| `ATM_UPLOADS_DIR` | каталог загруженных аудио (по умолчанию `$ATM_DATA_DIR/uploads`) |
| `ATM_OLLAMA_BASE_URL` | URL Ollama (по умолчанию `http://127.0.0.1:11434`) |
| `ATM_OLLAMA_MODEL` | тег модели в Ollama |
| `ATM_OFFLINE` | офлайн: Whisper без скачивания, Ollama `trust_env=false` |
| `ATM_WHISPER_LOCAL_ONLY` | только локальные веса Whisper (без загрузки из сети) |
| `ATM_WHISPER_DOWNLOAD_ROOT` | каталог кэша CTranslate2 / весов Whisper (опционально) |
| `ATM_OLLAMA_NUM_CTX`, `ATM_OLLAMA_NUM_PREDICT` | контекст и лимит ответа для саммари |
| `ATM_LOG_LEVEL` | `DEBUG`, `INFO`, … |

Полный список имён и значений по умолчанию — в `configs/app.example.yaml`.

---

## API в двух словах

- `POST /jobs` — форма: `audio_file`, `asr_model` (`fast` \| `medium` \| `high`), `summary_size` (`gist` \| `executive` \| `meeting`; для старых клиентов по-прежнему принимаются `short` \| `medium` \| `long` как синонимы), опционально `custom_prompt` — тогда саммари одним запросом к Ollama по вашей инструкции (иначе пресеты по `summary_size`).
- `GET /jobs` — список последних джобов (`limit`, `offset`), без больших полей.
- `GET /jobs/{id}` — статус и стадии.
- `GET /jobs/{id}/transcript` — транскрипт, как только ASR завершён (до готовности всего джоба); **425**, если транскрипта ещё нет; **409**, если джоб упал до транскрипта.
- `GET /jobs/{id}/result` — транскрипт и саммари, когда джоб `done`.
- `POST /jobs/{id}/requeue` — JSON `{ "asr_model", "summary_size", "custom_prompt"? }`: снова поставить джоб в очередь с тем же аудиофайлом (файл должен существовать на диске). Нельзя, пока джоб в `processing`.

## Почему саммари через Ollama может быть долгим

- **Длинный текст** → режим map-reduce: несколько последовательных вызовов LLM (чанки + финальный reduce), см. лог `mode` / `source_chunks` после джоба.
- **Тяжёлая модель** (например 14B) и **CPU** (`num_gpu=0` на части Mac) — больше секунд на токен.
- **Первый запрос** после старта Ollama — загрузка весов в память (особенно заметно на больших моделях).
- Уменьшите модель (`ATM_OLLAMA_MODEL`), длину входа или порог map-reduce (`ATM_SUMMARY_MAP_THRESHOLD`, `ATM_SUMMARIZER_MAX_INPUT_CHARS`, `ATM_SUMMARIZER_MAX_REDUCE_CHARS` — см. `configs/app.example.yaml` и `settings.py`).

---

## Структура репозитория

```
backend/app/     # FastAPI, ASR, саммари, джобы, настройки
frontend/        # статическая оболочка UI (если есть)
configs/         # пример переменных и комментариев (шпаргалка; код читает env в settings)
tests/
```

Лицензия и версия — в `pyproject.toml`.
