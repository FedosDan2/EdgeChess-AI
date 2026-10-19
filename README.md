# EdgeChess AI

Распознавание шахматной позиции на Firefly RK3588S: конвертация моделей в ONNX/RKNN, виртуальная камера в браузере, детекции и FEN. [Stockfish](STOCKFISH.md) даёт подсказку по запросу за выбранную сторону; TTS пока не подключён.

Используются веса и обучающие материалы из ветки `cv`; её устаревшие
пайплайны заменены общим runtime `vision` и не включены в текущую версию.
Новая 3D YOLOv8m — из `7e497a8`, дообученная YOLO11s — из `87545eb`:

| Профиль | Модели | Обработка |
|---|---|---|
| `2d` | YOLOv8n: `board2d`, `pieces2d` | Доска → обрезка bbox → фигуры → клетки |
| `3d` | YOLOv8m: `chess3d_m` (по умолчанию), YOLO11s: `chess3d` | Общий инференс фигур и четырёх углов → гомография → клетки |

ONNX работает на CPU; RKNN FP16/INT8 — через RKNN Lite на NPU. Веса находятся в `CV_2D/weights` и `CV_3D/weights`. Модели экспортируются отдельно в `convert/artifacts/<model>`. На ARM не нужны PyTorch, Ultralytics и полный Toolkit2.

Общие letterbox, DFL и NMS переиспользованы из `convert/common.py`. `vision` содержит загрузчик моделей, геометрию и два профиля. HTTP/WebSocket адаптер не содержит отдельного алгоритма распознавания. Новые профили добавляются через `vision/config.py` и `vision/pipeline.py`; выбор источника камеры независим от профиля.

## Основной запуск: NPU на Firefly

Для новой поставки со Stockfish используйте [инструкцию conda и архива](STOCKFISH.md#установка-на-firefly-только-внутри-conda).
Команды `run-web.sh` ниже относятся к прежнему установленному YOLO-runtime.

Основной вариант — **YOLOv8m, RKNN INT8, аппаратный NPU**. FP16 доступен
для сравнения в том же UI. На плате уже проверены реальный инференс и
переключение INT8 → FP16 → INT8.

Для установленного пакета задайте в терминале `APP_DIR` — каталог приложения
в согласованной рабочей папке платы, затем выполните:

```bash
cd "$APP_DIR"
bash run-web.sh
```

Подготовленный `run-web.sh` использует существующее conda-окружение,
библиотеки из `.deps` и запускает INT8 по умолчанию. Для старта с FP16:

```bash
EDGECHESS_BACKEND=rknn_fp16 bash run-web.sh
```

Откройте адрес платы с портом `8000` через свою настроенную сеть или
SSH-туннель. В поле **«Исполнитель»** переключайте **RKNN INT8 · NPU** и
**RKNN FP16 · NPU**. Адреса подключения и учётные данные задаются вне README.
В `/api/health` ожидаются `backend: rknn_int8` (либо `rknn_fp16`) и
`provider: RKNN NPU`. Автоматической замены NPU на CPU нет.

Для нового развёртывания, установки зависимостей и запуска без готового
скрипта используйте [инструкцию NPU](web/README.md#основной-запуск-на-npu).

## Подготовка моделей

Подробные команды: [конвертация](convert/README.md), [web-ui и Firefly](web/README.md). Фактические проверки и ограничения: [отчёт](convert/RUN_REPORT.md).

Создание синтетического YOLO-датасета на текущей 3D-сцене: [генератор датасета](web/frontend/DATASET.md).

```bash
cd convert
uv sync --locked
uv run python 01_download_samples.py --model chess3d
# Для новой модели нужен synthetic-2000 из генератора сцены (см. ссылку выше).
uv run python 01_download_samples.py --model chess3d_m --export ../data/synthetic-2000
# Для 2D нужен ROBOFLOW_API_KEY в окружении или корневом .env (игнорируется Git).
uv run python 01_download_samples.py --model board2d
uv run python 01_download_samples.py --model pieces2d
for model in board2d pieces2d chess3d chess3d_m; do
  uv run python 02_export_and_check.py --model "$model"
  uv run python 03_prepare_calibration.py --model "$model"
  uv run python 04_build_rknn.py --model "$model" --precision fp16
  uv run python 04_build_rknn.py --model "$model" --precision int8
  uv run python 06_check_postprocessing.py --model "$model"
done
```

Проверка INT8 может завершиться ненулевым кодом при превышении погрешности. RKNN и отчёт сохраняются для проверки качества в UI; статус такой конвертации виден в метаданных. Для новой YOLOv8m INT8 и FP16 прошли проверки конвертации и запуск на NPU.

## Дополнительный запуск: ONNX на локальном CPU

```bash
cd web/frontend
npm ci
npm run build
cd ..
uv sync --locked
EDGECHESS_PROFILE=3d EDGECHESS_3D_MODEL=chess3d_m EDGECHESS_BACKEND=onnx uv run uvicorn backend.app:app --host localhost --port 8000
```

Откройте `http://localhost:8000`. Эта команда выбирает профиль 3D, YOLOv8m и ONNX CPU для локальной проверки. Настройки запуска: `EDGECHESS_PROFILE`, `EDGECHESS_3D_MODEL`, `EDGECHESS_BACKEND`, `EDGECHESS_ARTIFACTS`, `EDGECHESS_THREADS`, `EDGECHESS_CONFIDENCE`. Интерфейс берёт начальную конфигурацию у сервера; `EDGECHESS_3D_MODEL=chess3d` выбирает прежнюю дообученную YOLO11s.

## Возможности интерфейса

- 2D-доска с SVG-фигурами и интерактивная 3D-сцена со столешницей.
- Три оформления, два процедурных набора 3D-фигур, настройка света и импорт GLB.
- Переключение профиля, двух 3D-моделей и ONNX/RKNN FP16/RKNN INT8; ошибка NPU показывается явно.
- Сохранение JPEG сцены и анализ загруженного JPEG после приостановки потока.
- Рамки, классы, расстановка, предупреждения о пропущенных углах и конфликтах клеток.
- Полный FEN из распознанной расстановки и явно заданных пользователем стороны хода, рокировок и взятия на проходе; счётчики пока 0 и 1.
- Метрики обработки, очереди, возраста кадра и экспорт JSON/CSV. Эталон позиции сцены используется только для сравнения результата, не для распознавания.

GLB должен содержать объекты `wP wN wB wR wQ wK bP bN bB bR bQ bK`, с осью Y вверх. Фигуры нормализуются по ширине; предел файла — 20 MiB. Встроенные фигуры отличаются от ChessRender360: качественная работа на исходном датасете не гарантирует её на процедурной сцене.

## Проверки

```bash
cd web
uv run pytest
cd frontend
npm test
npm run build
cd ../..
web/.venv/bin/python -m vision.evaluate --profile 3d
web/.venv/bin/python -m vision.evaluate --profile 2d
```

`vision.evaluate` проверяет исходную разметку небольшой выборки; это не полный mAP. Версии и исходный train/test конкретных весов не подтверждены автором, поэтому независимость выборки от обучения не гарантируется.

Обучающие скрипты и подготовка данных включены в репозиторий:
[2D](README_2D.md), [3D](README_3D.md). Перед будущим переобучением необходимо
исправить исходную подготовку 3D-данных: сейчас случайные аугментации
применяются также к `original`, `val` и `test`. Инференс поддерживается только
через общий модуль `vision`, без старых `CV_2D/pipeline` и `CV_3D/pipeline`.
