# EdgeChess AI

Распознавание шахматной позиции на Firefly RK3588S: конвертация моделей в ONNX/RKNN, виртуальная камера в браузере, детекции и FEN. Stockfish пока не подключён.

Используются веса из ветки `cv`, без слияния её устаревшего runtime.
Новая 3D YOLOv8m — из `7e497a8`, дообученная YOLO11s — из `87545eb`:

| Профиль | Модели | Обработка |
|---|---|---|
| `2d` | YOLOv8n: `board2d`, `pieces2d` | Доска → обрезка bbox → фигуры → клетки |
| `3d` | YOLOv8m: `chess3d_m` (по умолчанию), YOLO11s: `chess3d` | Общий инференс фигур и четырёх углов → гомография → клетки |

ONNX работает на CPU; RKNN FP16/INT8 — через RKNN Lite на NPU. Веса находятся в `CV_2D/weights` и `CV_3D/weights`. Модели экспортируются отдельно в `convert/artifacts/<model>`. На ARM не нужны PyTorch, Ultralytics и полный Toolkit2.

Общие letterbox, DFL и NMS переиспользованы из `convert/common.py`. `vision` содержит загрузчик моделей, геометрию и два профиля. HTTP/WebSocket адаптер не содержит отдельного алгоритма распознавания. Новые профили добавляются через `vision/config.py` и `vision/pipeline.py`; выбор источника камеры независим от профиля.

## Подготовка и запуск

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

Проверка INT8 может завершиться ненулевым кодом при превышении погрешности. RKNN и отчёт сохраняются для проверки качества в UI; статус такой конвертации виден в метаданных. FP16 рекомендуется как отправная точка.

```bash
cd web/frontend
npm ci
npm run build
cd ..
uv sync --locked
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Откройте `http://127.0.0.1:8000`. По умолчанию выбран профиль 3D, YOLOv8m и ONNX. Настройки запуска: `EDGECHESS_PROFILE`, `EDGECHESS_3D_MODEL`, `EDGECHESS_BACKEND`, `EDGECHESS_ARTIFACTS`, `EDGECHESS_THREADS`, `EDGECHESS_CONFIDENCE`. Интерфейс берёт начальную конфигурацию у сервера; `EDGECHESS_3D_MODEL=chess3d` выбирает прежнюю дообученную YOLO11s.

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

Исходные обучающие скрипты и описания остаются в ветке `cv`. Для будущего переобучения необходимо исправить её подготовку 3D-данных: сейчас случайные аугментации применяются также к `original`, `val` и `test`.
