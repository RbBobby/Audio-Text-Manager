# Audio Text Manager

Локальный сервис: загрузка аудио (и видео **mp4**, из которого берётся только звук) → **распознавание речи** ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) → **саммари** через [Ollama](https://ollama.com/) (`/api/chat`). API на **FastAPI**, фоновые джобы — воркер в том же процессе.

## Требования

| Компонент | Зачем |
|-----------|--------|
| **Python 3.10+** | бэкенд и тесты |
| **ffmpeg** (+ **ffprobe** в составе ffmpeg) | нормализация аудио перед Whisper; для `.mp4` извлекается первая аудиодорожка |
| **Ollama** | LLM для саммари (локально, `http://127.0.0.1:11434` по умолчанию) |
| **Интернет** (первый запуск) | скачивание весов Whisper и модели Ollama |

Опционально: **CUDA** (Windows/Linux) — если сборка `ctranslate2` с GPU; иначе faster-whisper на CPU (на Apple Silicon часто через Metal, если поддерживается сборкой).

---

## Whisper и faster-whisper

**Whisper** в этом проекте — модель **распознавания речи** в архитектуре [OpenAI Whisper](https://github.com/openai/whisper). Она **не** вызывается «как в оригинальной статье» через чистый PyTorch в рантайме джоба: для инференса используется **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** на движке **[CTranslate2](https://github.com/OpenNMT/CTranslate2)** (ускорение на CPU и при наличии — на GPU).

| Что | Где в проекте / как задаётся |
|-----|------------------------------|
| Зависимость | `faster-whisper` в `pyproject.toml`; ставится вместе с `pip install -e .` |
| Нормализация аудио перед ASR | **ffmpeg** (обязателен в `PATH`) — см. `backend/app/asr/ffmpeg_normalize.py`; для `.mp4` берётся поток `0:a:0`, видео не кодируется |
| Пресеты скорости/качества | `backend/app/asr/presets.py` → в API поле `asr_model`: `fast` / `medium` / `high` |
| Соответствие чекпоинтам Systran | `fast` → `small`, `medium` → `medium`, `high` → `large-v3` |
| Кэш весов и офлайн | Переменные `ATM_WHISPER_DOWNLOAD_ROOT`, `ATM_WHISPER_LOCAL_ONLY`, `ATM_OFFLINE` (см. ниже и `configs/app.example.yaml`) |

**Первый запуск транскрибации:** веса модели **скачиваются автоматически** (как правило в кэш Hugging Face в домашнем каталоге пользователя, если не задан `ATM_WHISPER_DOWNLOAD_ROOT`). Нужен доступ в интернет, если не включён офлайн-режим.

**Ориентир по диску под веса Whisper:** от порядка **~1 GB** (`small`) до **нескольких GB** (`large-v3`), плюс отдельно место под модель **Ollama** для саммари.

**Офлайн только для Whisper:** `ATM_WHISPER_LOCAL_ONLY=1` — без загрузок из сети; веса должны уже быть в кэше или в `ATM_WHISPER_DOWNLOAD_ROOT`. Полный офлайн приложения: `ATM_OFFLINE=1` (также влияет на Ollama, см. `settings.py`).

---

## Установка с нуля

Общий порядок: **Python 3.10+ и ffmpeg в PATH → Ollama с моделью → `make install` → `make run`**. Каталог репозитория в примерах: `audio-text-manager`.

### Make

Из **корня репозитория**. Venv создаётся сам (`.venv`); активировать его не нужно.

| Цель | macOS / Linux | Windows (cmd) | Зачем |
|------|---------------|---------------|--------|
| Справка | `make` / `make help` | `make.bat` | список целей |
| Зависимости | `make install` | `make.bat install` | `.venv` + `pip install -e ".[dev]"` (pytest, ruff, pre-commit, faster-whisper) |
| Сервер | `make run` | `make.bat run` | [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/) |
| С `--reload` | `make dev` | `make.bat dev` | правки Python/HTML подхватываются без ручного рестарта |
| Тесты | `make test` | `make.bat test` | pytest; нужен ffmpeg |
| Линтер | `make lint` | `make.bat lint` | Ruff, как CI `.github/workflows/lint.yml` |
| Git hook | `make pre-commit` | `make.bat pre-commit` | ruff `--fix` на staged `.py` |
| Ollama CPU | `make ollama-cpu` | — | `OLLAMA_NUM_GPU=0 ollama serve` (обход Metal на Apple Silicon) |

Типичный старт (ffmpeg уже в PATH, Ollama слушает `11434`):

```bash
git clone <URL-репозитория> audio-text-manager
cd audio-text-manager
make install
make run
```

Windows **без GNU Make**: `make.bat install` и `make.bat run` (в PowerShell: `.\make.bat run`). Если установлен GNU Make (Git Bash / chocolatey), те же цели: `make install`, `make run`.

Другой порт: `make run PORT=8001` или `set PORT=8001 && make.bat run`. Хост: `HOST=0.0.0.0`.

Перед `make run` нужен **запущенный Ollama**. На Mac при падениях Metal сначала Quit Ollama, затем `make ollama-cpu` (или `make ollama-metal`).

Без Make, venv активирован вручную:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Шаг 0. Клонирование (все ОС)

```bash
git clone <URL-репозитория> audio-text-manager
cd audio-text-manager
```

Дальше достаточно **`make install`** (или `make.bat install`) — см. [Make](#make). Ручной venv нужен только если Make нет:

| ОС | Команды |
|----|---------|
| **macOS / Linux** | `python3 -m venv .venv && source .venv/bin/activate` |
| **Windows (cmd)** | `python -m venv .venv` затем `.venv\Scripts\activate.bat` |
| **Windows (PowerShell)** | `python -m venv .venv` затем `.\.venv\Scripts\Activate.ps1` |

Если PowerShell ругается на политику выполнения: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (один раз для пользователя).

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

Флаг `-e` (editable) нужен, чтобы импорт `backend.app` работал из корня проекта. Без pytest/ruff: `pip install -e .`

На этом шаге в виртуальное окружение попадает пакет **`faster-whisper`**. Отдельной команды вида `brew install whisper` нет — только `pip` и `pyproject.toml`.

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
   - Библиотека **уже установлена** вместе с проектом (`make install` → зависимость `faster-whisper`). Это не отдельный продукт «Whisper.app», а Python-пакет поверх **CTranslate2**.  
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
   - Если в терминале **`command not found: ollama`**: установите Ollama ([dmg](https://ollama.com/download/mac) или `brew install --cask ollama`), **перезапустите терминал**; при необходимости один раз откройте приложение **Ollama** из «Программы». На Mac с Homebrew проверьте, что в `PATH` есть `/opt/homebrew/bin` (Apple Silicon) или `/usr/local/bin` (Intel).
   - Список загруженных моделей: **`ollama list`** (команда без `--`).

5. **Apple Silicon и падения Ollama / Metal (HTTP 500, `llama runner process has terminated`)**  
   Переменные задаются для **процесса `ollama serve`**. Если Ollama уже запущен из приложения или без них, **сначала полностью выйдите** (значок в строке меню → Quit) или выполните `killall Ollama`, затем поднимите сервер заново.

   Чаще всего хотят обойти краш без «хака» частичного отключения Metal-тензоров: полностью выключите GPU для LLM (**медленнее**, зато типичный чистый путь на CPU для Ollama):

   ```bash
   OLLAMA_NUM_GPU=0 ollama serve
   ```  

   Либо из репозитория:

   ```bash
   make ollama-cpu
   ```

   Если без GPU всё ещё падает: `make ollama-metal` (`GGML_METAL_TENSOR_DISABLE=1`, [ollama/ollama#14432](https://github.com/ollama/ollama/issues/14432)).

   Проверка в другом терминале: `ollama run qwen2.5:7b-instruct-q4_K_M "ok"`.

6. **Запуск приложения** (Ollama уже слушает порт) — [Make](#make):

   ```bash
   make install
   make run
   ```

7. **Проверка в браузере**  
   - API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
   - UI: [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/)

8. **Тесты и линтер** (нужен ffmpeg): `make test`, `make lint`, при желании `make pre-commit`.

---

### Установка на Windows

1. **Python 3.10+**  
   - Установщик с [python.org](https://www.python.org/downloads/windows/) — **включите «Add python.exe to PATH»**  
   - Либо: `winget install Python.Python.3.12`  
   - Закройте и снова откройте терминал после установки. Проверка: `python --version`

2. **Зависимости** — [Make](#make): `make.bat install` (PowerShell: `.\make.bat install`). GNU Make не обязателен.

3. **ffmpeg** (обязательно в `PATH`, вместе с `ffprobe`)  
   Один из вариантов:  
   - [winget](https://winget.run/pkg/Gyan.FFmpeg): `winget install Gyan.FFmpeg`  
   - [Chocolatey](https://chocolatey.org/): `choco install ffmpeg`  
   - [Scoop](https://scoop.sh/): `scoop install ffmpeg`  
   Новый терминал → `ffmpeg -version` и `ffprobe -version`

4. **Whisper (faster-whisper)** — транскрибация  
   - Устанавливается **вместе с проектом** на шаге 2 (`make.bat install` → `faster-whisper`). Отдельного установщика Whisper для ASR не требуется.  
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
   - Список моделей: **`ollama list`**. Если **`ollama` не распознаётся** — переустановите с [ollama.com/download/windows](https://ollama.com/download/windows), откройте новый терминал; при необходимости добавьте каталог установки Ollama в **PATH** пользователя (см. настройки установщика / документацию Ollama).

6. **Запуск** (Ollama уже слушает порт): `make.bat run` (PowerShell: `.\make.bat run`). Другой порт: `set PORT=8001 && make.bat run`.

7. **Проверка**  
   - [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
   - [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/)

8. **Тесты и линтер** (нужен ffmpeg): `make.bat test`, `make.bat lint`, `make.bat pre-commit`.

Если на «чистом» Windows возникают проблемы со сборкой **faster-whisper** / CTranslate2, имеет смысл поставить [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) или использовать **WSL2** (Ubuntu) и шаги как для Linux: `sudo apt install ffmpeg make`, затем `make install && make run`.

---

### Linux (кратко)

```bash
sudo apt update && sudo apt install -y ffmpeg python3 python3-venv make
# Ollama: https://ollama.com/download/linux
ollama pull qwen2.5:14b-instruct-q4_K_M
make install && make run
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
| `ATM_MAX_UPLOAD_BYTES` | лимит размера аудио (wav/mp3/m4a/flac/ogg), по умолчанию 500 MB |
| `ATM_MAX_VIDEO_UPLOAD_BYTES` | лимит размера `.mp4` до извлечения звука, по умолчанию 4 GB |
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

- `POST /jobs` — форма: `audio_file` (аудио или `.mp4` с звуком), `asr_model` (`fast` \| `medium` \| `high`), `summary_size` (`gist` \| `executive` \| `meeting`; для старых клиентов по-прежнему принимаются `short` \| `medium` \| `long` как синонимы), опционально `custom_prompt` — тогда саммари одним запросом к Ollama по вашей инструкции (иначе пресеты по `summary_size`).
- `GET /jobs` — список последних джобов (`limit`, `offset`), без больших полей.
- `GET /jobs/{id}` — статус и стадии.
- `GET /jobs/{id}/transcript` — транскрипт, как только ASR завершён (до готовности всего джоба); **425**, если транскрипта ещё нет; **409**, если джоб упал до транскрипта.
- `GET /jobs/{id}/result` — транскрипт и саммари, когда джоб `done`.
- `POST /jobs/{id}/requeue` — JSON `{ "asr_model", "summary_size", "custom_prompt"? }`: снова поставить джоб в очередь с тем же аудиофайлом (файл должен существовать на диске). Нельзя, пока джоб в `processing`.
- `POST /jobs/{id}/cancel`, `POST /jobs/cancel-active` — остановить одну задачу или все задачи в статусах `queued` / `processing`.

## Почему саммари через Ollama может быть долгим

- **Длинный текст** → режим map-reduce: несколько последовательных вызовов LLM (чанки + финальный reduce), см. лог `mode` / `source_chunks` после джоба.
- **Тяжёлая модель** (например 14B) и **CPU** (`num_gpu=0` на части Mac) — больше секунд на токен.
- **Первый запрос** после старта Ollama — загрузка весов в память (особенно заметно на больших моделях).
- Уменьшите модель (`ATM_OLLAMA_MODEL`), длину входа или порог map-reduce (`ATM_SUMMARY_MAP_THRESHOLD`, `ATM_SUMMARIZER_MAX_INPUT_CHARS`, `ATM_SUMMARIZER_MAX_REDUCE_CHARS` — см. `configs/app.example.yaml` и `settings.py`).

---

## Структура репозитория

```
Makefile         # make install / run / test / lint (macOS, Linux, GNU Make на Windows)
make.bat         # те же цели в cmd/PowerShell без GNU Make
backend/app/     # FastAPI, ASR, саммари, джобы, настройки
frontend/        # статическая оболочка UI
configs/         # пример переменных (шпаргалка; код читает env в settings)
tests/
```

Лицензия и версия — в `pyproject.toml`.
