# Web-ui

FastAPI, один inference-worker, ACK и очередь из одного свежего кадра; предыдущий ожидающий кадр заменяется. Профили и ONNX/RKNN используют общий код `vision`. JPEG потока ограничен 2 MiB; отдельный JPEG — 16 MiB и 4096×4096. Одновременно обрабатывается одна камера или HTTP-запрос; занятый worker возвращает 1013/409.

## Локальный запуск

Сначала экспортируйте модели по [convert/README.md](../convert/README.md).

```bash
cd frontend
npm ci
npm run build
cd ..
uv sync --locked
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

По умолчанию `EDGECHESS_PROFILE=3d`, `EDGECHESS_BACKEND=onnx`, `EDGECHESS_THREADS=4`, `EDGECHESS_CONFIDENCE=0.5`. Каталог моделей задаётся `EDGECHESS_ARTIFACTS`, по умолчанию `convert/artifacts` в корне проекта. Поддерживаются `2d|3d` и `onnx|rknn_fp16|rknn_int8`. CPU и NPU выбираются явно, без автоматической подмены.

В интерфейсе выбирайте отдельно источник 2D/3D и соответствующий профиль; это позволяет проверять неподходящие кадры осознанно. Для загруженного JPEG сначала приостановите поток. Кадр показывается с рамками и распознанной позицией. Переключение backend освобождает предыдущие модели; ошибка конфигурации прекращает поток и позволяет выбрать доступный исполнитель.

## Firefly

Сначала проверьте свободное место, RAM и существующие нагрузки. В рамках текущей задачи разрешена только папка `~/EDGE/24942/STUDBULLS`; нельзя удалять чужие файлы или останавливать чужие процессы. При недостатке ресурсов выполняйте работу локально.

Минимальный архив собирается локально, после frontend build и конвертации:

```bash
python3 tools/package_firefly.py --profiles 2d 3d --backends rknn_fp16 rknn_int8
```

По умолчанию упаковщик включает только профиль 3D и FP16; можно указать `--output`. В архиве runtime, зависимости, frontend и выбранные модели; нет PT, ONNX для NPU-only пакета, датасетов, окружений и полных изображений отчётов. Скрипт сам ничего не отправляет на плату.

После проверки ресурсов перенесите и распакуйте архив только в указанную рабочую папку. Все cache/tmp/venv также должны находиться в ней. Из этой папки:

```bash
mkdir -p .tmp .cache
export TMPDIR="$PWD/.tmp"
export PIP_CACHE_DIR="$PWD/.cache/pip"
python3 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r web/requirements-firefly.txt
EDGECHESS_PROFILE=3d EDGECHESS_BACKEND=rknn_fp16 .venv/bin/python -m uvicorn web.backend.app:app --host 0.0.0.0 --port 8000
```

Упаковщик формирует `requirements-firefly.txt` из закреплённого `web/uv.lock` через локальный uv, поэтому на плате можно использовать обычный pip. Если uv уже имеется на плате:

```bash
cd web
UV_CACHE_DIR="$PWD/../.cache/uv" UV_PROJECT_ENVIRONMENT="$PWD/../.venv" uv sync --locked --no-dev --extra rknn
EDGECHESS_PROFILE=3d EDGECHESS_BACKEND=rknn_fp16 ../.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

RKNN Lite 2.3.2 должен быть совместим с установленным драйвером/`librknnrt`; это подтверждается только запуском на NPU. Python ARM64 3.10–3.12 поддержан lock-файлом. Установку и совместимость на Firefly в этом проходе не проверяли из-за заполненного диска.

## Метрики и тесты

```bash
uv run pytest
cd frontend
npm test
npm run build
```

Бенчмарк из `web`, на заранее загруженных изображениях:

```bash
uv run python -m backend.benchmark --profile 3d --backend onnx --runs 100 /path/to/frame.jpg
```

Он измеряет полный пайплайн: letterbox, модель(и), NMS и геометрию, без JPEG/сети/отрисовки. Для Firefly выберите `rknn_fp16` или `rknn_int8`. JSON/CSV UI дополнительно содержит метрики возраста кадра и очереди; сравнивайте backends на одном сохранённом JPEG.

SVG 2D-фигуры: cburnett из Lichess, [лицензия](frontend/public/pieces/cburnett/LICENSE.md) CC BY-SA 3.0.

Браузерная регрессия управления (при запущенном UI):

```bash
cd web/frontend
npx playwright install chromium
EDGECHESS_WEB_URL=http://127.0.0.1:8000 npm run test:browser
```

Тест проверяет доступ мыши к сцене, ходы обеих сторон в 3D, вращение, точный сброс камеры и ход в 2D. Chromium требует свои системные библиотеки; браузер и Playwright нужны только локально для разработки и не входят в архив Firefly.
