# Конвертация моделей

## Требования и модели

Linux x86_64, uv, Python 3.10; зависимости закреплены в `convert/uv.lock`.
PyTorch выполняется на CPU, RKNN Toolkit2 — только на машине конвертации.
На Firefly используется RKNN Lite2, не полный Toolkit2.

| Ключ | Веса | Назначение |
|---|---|---|
| `board2d` | `CV_2D/weights/best_board_detect.pt` | Доска |
| `pieces2d` | `CV_2D/weights/best_board_and_pieces.pt` | Фигуры на обрезке доски |
| `chess3d_m` | `CV_3D/weights/best_new_scratch.pt` | YOLOv8m, профиль 3D по умолчанию |
| `chess3d` | `CV_3D/weights/best_3d_detection.pt` | Дообученная YOLO11s |

## Подготовка выборки

Из корня репозитория:

```bash
cd convert
uv sync --locked
uv run --locked python 01_download_samples.py --model chess3d_m --export ../data/synthetic-2000
```

Для `chess3d_m` нужен [синтетический набор](dataset.md) с `train/images` и
`test/images`. По умолчанию используются 128 калибровочных и 32 тестовых кадра.

Альтернативные источники:

```bash
uv run --locked python 01_download_samples.py --model chess3d
uv run --locked python 01_download_samples.py --model board2d
uv run --locked python 01_download_samples.py --model pieces2d
```

`chess3d` использует ChessRender360 v5. Roboflow требует `ROBOFLOW_API_KEY`
в окружении или корневом `.env`; `--version` закрепляет версию набора.
Для локального YOLO-экспорта используйте `--export /path/to/dataset`.

## Экспорт и калибровка

Команды выполняются из `convert/`; замените `MODEL` нужным ключом:

```bash
MODEL=chess3d_m
uv run --locked python 02_export_and_check.py --model "$MODEL"
uv run --locked python 03_prepare_calibration.py --model "$MODEL"
uv run --locked python 04_build_rknn.py --model "$MODEL" --precision fp16
uv run --locked python 04_build_rknn.py --model "$MODEL" --precision int8
uv run --locked python 06_check_postprocessing.py --model "$MODEL"
```

Для `pieces2d` сначала экспортируйте `board2d`: калибровка использует найденные
ею обрезки. Результаты сохраняются в `convert/artifacts/<model>/`:

- `model.onnx` — CPU runtime; `model_split.onnx` — вход конвертации RKNN.
- `model.json` — классы, параметры входа и SHA256.
- `rknn_fp16/`, `rknn_int8/` — `model.rknn` и `comparison.json`.

Контракт: batch 1, 640×640, RGB, letterbox 114, внешний NMS.
ONNX — float32 NCHW /255; RKNN — uint8 NHWC, нормализация /255 внутри графа.

Шаг `02` сравнивает PyTorch и ONNX, `06` сверяет preprocessing/NMS с Ultralytics.
Шаг `04` проверяет численный перенос в симуляторе: precision/recall совпадения
≥95% при confidence 0.25 и IoU 0.9. Ненулевой код возврата означает превышение
погрешности; это не оценка mAP или производительности NPU.

Для численной проверки на отдельных изображениях у шага `02` есть
`--verification-directory`. Алгоритм INT8 задаётся у шага `04`:
`--algorithm normal|mmse|kl_divergence` (по умолчанию `normal`).
