# Web-ui

Подсказка Stockfish, история виртуальной партии, CPU-проверка и новая поставка
для conda на Firefly: [STOCKFISH.md](../STOCKFISH.md). Рекомендация по кнопке,
не выполняет ход; по умолчанию нужны совпадающие результаты YOLO. TTS пока нет.
Старые команды `run-web.sh` ниже описывают прежнюю установку без Stockfish.

FastAPI, один inference-worker, ACK и очередь из одного свежего кадра; предыдущий ожидающий кадр заменяется. Профили и ONNX/RKNN используют общий код `vision`. JPEG потока ограничен 2 MiB; отдельный JPEG — 16 MiB и 4096×4096. Одновременно обрабатывается одна камера или HTTP-запрос; занятый worker возвращает 1013/409.

## Основной запуск на NPU

Основной режим — `3d`, новая YOLOv8m (`chess3d_m`), `rknn_int8`.
Для сравнения доступен `rknn_fp16`; оба варианта проверены на настоящем NPU.
ONNX CPU — дополнительный режим локальной проверки.

Адрес платы, SSH-логин, пароль и персональные пути задавайте в своём
окружении или SSH-конфигурации. Не сохраняйте их в Markdown и Git.
В примерах `APP_DIR` — каталог runtime в разрешённой рабочей папке платы.

### Уже установленный пакет

На плате выполните:

```bash
cd "$APP_DIR"
bash run-web.sh
```

Подготовленный скрипт использует существующий conda Python и локальный
каталог `.deps`, направляет временные файлы и кеши в папку приложения.
По умолчанию выбирается INT8. Для старта с FP16:

```bash
EDGECHESS_BACKEND=rknn_fp16 bash run-web.sh
```

Откройте адрес платы с портом `8000` через свою сеть или настроенный
SSH-туннель. В поле **«Исполнитель»** выбирайте **RKNN INT8 · NPU** или
**RKNN FP16 · NPU**. Переключение происходит без перезапуска web-ui;
предыдущая inference-сессия освобождается.

В `/api/health` проверьте `status: ready`, `model: chess3d_m`,
`backend: rknn_int8` (либо `rknn_fp16`), `provider: RKNN NPU`.
Автоматической замены NPU на CPU нет. В минимальном пакете установлены
только YOLOv8m и два RKNN-backend; для 2D или прежней YOLO11s нужно
добавить соответствующие артефакты.

### Если браузер не открывает адрес платы

Строки `Application startup complete` и `Uvicorn running` означают, что
сервер запустился. Предупреждение о `RKNN_QUERY_INPUT_DYNAMIC_RANGE` у
статической модели само по себе не является ошибкой запуска.

Проверьте доступ к `/api/health` и настройки прокси/VPN. В проверенной
конфигурации запрос без HTTP-прокси работал, а запрос через прокси зависал.
Для такого случая используйте SSH-туннель. На своём компьютере задайте
`EDGECHESS_SSH_ALIAS` — алиас платы из личной SSH-конфигурации — и выполните:

```bash
ssh -N -L localhost:18000:localhost:8000 "${EDGECHESS_SSH_ALIAS:?Укажите SSH-алиас платы}"
```

Пока эта SSH-сессия открыта и сервер на плате работает, открывайте
`http://localhost:18000`. Инференс остаётся на NPU платы; локальный порт
только передаёт трафик. Сам сервер запускается отдельной командой
`bash run-web.sh` на плате. Туннель не запускает сервер. Если приложение
остановлено, доступ по обоим адресам прекращается.


### Новое развёртывание

Сначала проверьте свободное место, RAM и существующие нагрузки. Работайте
только в согласованной рабочей папке; нельзя удалять чужие файлы или
останавливать чужие процессы. При недостатке ресурсов остановите размещение.

На локальной x86-машине экспортируйте модели по
[convert/README.md](../convert/README.md), соберите frontend и минимальный архив.
Команды выполняются из корня репозитория:

```bash
npm --prefix web/frontend ci
npm --prefix web/frontend run build
python3 tools/package_firefly.py --profiles 3d --3d-models chess3d_m --backends rknn_int8 rknn_fp16 --output artifacts/firefly-runtime.tar
```

В архиве — runtime, frontend, выбранные RKNN, metadata и
`web/requirements-firefly.txt`. Датасеты, PT, ONNX, venv и полный RKNN Toolkit
не переносятся. Библиотеки Python упаковщик не устанавливает и не отправляет;
подготовленный пакет с `.deps` дополнительно содержит недостающие ARM64-библиотеки.

При необходимости включите обе 3D-модели и 2D-каскад:

```bash
python3 tools/package_firefly.py --profiles 2d 3d --3d-models chess3d_m chess3d --backends rknn_fp16 rknn_int8
```

Для одной прежней модели используйте `--3d-models chess3d` и при запуске
`EDGECHESS_3D_MODEL=chess3d`. Список профилей и backends в пакете ограничивает
доступные варианты инференса. По умолчанию упаковщик включает новую 3D-модель
и FP16, поэтому для обоих NPU-вариантов явно указывайте два backend.

Перенесите и распакуйте пакет в отдельный каталог приложения внутри
разрешённой рабочей папки. Для подключения используйте свою SSH-конфигурацию;
адреса и учётные данные в инструкции не фиксируются. Все cache/tmp/venv/.deps
должны оставаться в этой рабочей папке.

### Запуск без готового run-web.sh

Активируйте подходящее conda-окружение. `EDGECHESS_ENV` — его имя или путь,
`EDGECHESS_BIND_HOST` — выбранный адрес прослушивания, заданный в терминале.
Python ARM64 должен быть версии 3.10–3.12, RKNN Lite — 2.3.2 с совместимым
драйвером/`librknnrt`. Проверка импортов:

```bash
conda activate "$EDGECHESS_ENV"
cd "$APP_DIR"
PYTHONPATH="$PWD/.deps${PYTHONPATH:+:$PYTHONPATH}" python -B -c "import numpy, cv2, fastapi, uvicorn, anyio, PIL; from rknnlite.api import RKNNLite; print('Imports OK')"
```

Если окружение содержит NPU-библиотеки, но не содержит web-зависимости,
установите только недостающие пакеты в `.deps`, не меняя conda:

```bash
mkdir -p .tmp .cache .config
export TMPDIR="$PWD/.tmp"
export PIP_CACHE_DIR="$PWD/.cache/pip"
python -m pip install --no-cache-dir --target .deps --constraint web/requirements-firefly.txt fastapi uvicorn anyio Pillow websockets
```

Ограничения версий берутся из `web/requirements-firefly.txt`, который входит
в пакет и сформирован из lock-файла. Для полного нового окружения вместо этого можно создать `.venv` внутри
рабочей папки и установить `web/requirements-firefly.txt`, сформированный
из `web/uv.lock`. Это требует больше места. PyTorch и полный Toolkit2 на плате
не нужны. После подготовки окружения запустите из каталога runtime:

```bash
mkdir -p .tmp .cache .config
export TMPDIR="$PWD/.tmp"
export XDG_CACHE_HOME="$PWD/.cache"
export XDG_CONFIG_HOME="$PWD/.config"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.deps${PYTHONPATH:+:$PYTHONPATH}"
EDGECHESS_PROFILE=3d EDGECHESS_3D_MODEL=chess3d_m EDGECHESS_BACKEND=rknn_int8 python -B -m uvicorn web.backend.app:app --host "${EDGECHESS_BIND_HOST:?Задайте адрес прослушивания}" --port 8000 --loop asyncio --ws websockets
```

Для старта с FP16 замените `rknn_int8` на `rknn_fp16`. В текущем размещении
проверены оба NPU-backend и переключение через UI. Одного успешного импорта
RKNN Lite для подтверждения совместимости драйвера недостаточно — нужен
реальный инференс.

## Дополнительный локальный запуск на CPU

Из корня репозитория, после экспорта ONNX:

```bash
npm --prefix web/frontend ci
npm --prefix web/frontend run build
cd web
uv sync --locked
EDGECHESS_PROFILE=3d EDGECHESS_3D_MODEL=chess3d_m EDGECHESS_BACKEND=onnx uv run uvicorn backend.app:app --host localhost --port 8000
```

Откройте `http://localhost:8000`. Эта команда явно выбирает ONNX CPU.

## Выбор профиля и модели

Настройки: `EDGECHESS_PROFILE`, `EDGECHESS_3D_MODEL`, `EDGECHESS_BACKEND`,
`EDGECHESS_ARTIFACTS`, `EDGECHESS_THREADS` (4), `EDGECHESS_CONFIDENCE` (0.5).
Каталог артефактов по умолчанию — `convert/artifacts` в корне runtime.
Поддерживаются `2d|3d` и `onnx|rknn_fp16|rknn_int8`; исполнитель выбирается явно.

В 3D можно выбрать YOLOv8m (`chess3d_m`) или прежнюю дообученную YOLO11s
(`chess3d`), если соответствующие артефакты установлены. В 2D селектор модели
скрывается и используется каскад board2d → pieces2d.

HTTP `/api/analyze` и WebSocket `/api/stream` принимают необязательный параметр
`model=chess3d_m|chess3d` вместе с `profile=3d`. Без него выбирается модель
из `EDGECHESS_3D_MODEL`; при `profile=2d` выбор 3D-модели игнорируется.
Список установленных моделей возвращается в `model_choices` ответа `/api/health`.

Источник 2D/3D и профиль выбираются отдельно. Для анализа загруженного JPEG
приостановите поток. Ошибка конфигурации прекращает поток и позволяет выбрать
другой установленный исполнитель; автоматического fallback нет.

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
EDGECHESS_WEB_URL=http://localhost:8000 npm run test:browser
```

`npm run test:models` проверяет настоящий поток инференса при переключении
YOLOv8m → YOLO11s → 2D → YOLO11s → YOLOv8m.

Тест проверяет доступ мыши к сцене, ходы обеих сторон в 3D, вращение, точный сброс камеры и ход в 2D. Chromium требует свои системные библиотеки; браузер и Playwright нужны только локально для разработки и не входят в архив Firefly.
