# Конвертация моделей

Две 3D-модели сохраняются независимо: `chess3d` — прежняя дообученная YOLO11s,
`chess3d_m` — новая YOLOv8m (`CV_3D/weights/best_new_scratch.pt`).
Артефакты находятся в `artifacts/<model>`, поэтому конвертация одной модели
не перезаписывает другую. По умолчанию web-ui использует `chess3d_m`.

Для новой модели используйте существующий synthetic-2000, без повторного
скачивания и копирования исходных изображений:

```bash
cd convert
uv run python 01_download_samples.py --model chess3d_m --export ../data/synthetic-2000
uv run python 02_export_and_check.py --model chess3d_m
uv run python 03_prepare_calibration.py --model chess3d_m
uv run python 04_build_rknn.py --model chess3d_m --precision fp16
uv run python 04_build_rknn.py --model chess3d_m --precision int8
uv run python 06_check_postprocessing.py --model chess3d_m
```

Регистрация изображений сохраняет manifest в `data/synthetic3d`; калибровочные
PNG создаются там же. Источники калибровки задаются отдельно от весов через
общую конфигурацию `vision/config.py`. Старый `chess3d` продолжает использовать
свой ChessRender360 manifest и калибровку. Проверки конвертации сравнивают
исполнители на одинаковых кадрах; повторная оценка качества обучения не нужна.

Linux x86_64, Python 3.10, CPU PyTorch, RKNN Toolkit2 2.3.2. Зависимости закреплены в `uv.lock`; установки CUDA не требуется. Не устанавливайте полный Toolkit2 на Firefly.

## Данные

```bash
uv sync --locked
uv run python 01_download_samples.py --model chess3d
uv run python 01_download_samples.py --model board2d
uv run python 01_download_samples.py --model pieces2d
```

ChessRender360 v5 скачивается по отдельным файлам Kaggle: только RGB и JSON, без depth/semantic/instance. По умолчанию 128 калибровочных и 32 тестовых кадра; отдельные группы, seed 42 для разбиения как в `cv`, seed 43 для подвыборки. Manifest содержит ID, split, источник и SHA256. Совпадение версии и разбиения с фактическим обучением весов требует подтверждения автора.

Roboflow требует `ROBOFLOW_API_KEY` в окружении или корневом `.env`. Выбирается последняя опубликованная версия: при выполненной проверке board v2 и pieces v4. Альтернатива: `--export /path/to/unpacked/yolov8` с `data.yaml`, `train/images`, `train/labels`, `test/images`, `test/labels`. `--version` позволяет закрепить версию. Ключ и ссылки с токенами не сохраняются в manifest.

Классы сопоставляются по `data.yaml`: для досок оставляется `chessboard`; фигуры сопоставляются классам 1–12 весов, без предположения о порядке классов в экспорте. Класс 0 модели фигур остаётся зарезервированным под доску, в актуальном Roboflow v4 таких меток нет.

## Экспорт и проверки

Запускайте последовательно для каждой модели; для подготовки обрезок фигур сначала экспортируйте `board2d`:

```bash
uv run python 02_export_and_check.py --model chess3d
uv run python 03_prepare_calibration.py --model chess3d
uv run python 04_build_rknn.py --model chess3d --precision fp16
uv run python 04_build_rknn.py --model chess3d --precision int8
uv run python 06_check_postprocessing.py --model chess3d
```

Такие же команды поддерживают `board2d` и `pieces2d`. Экспорт: статические 640×640, opset 12, batch 1, external NMS. Обычный ONNX используется CPU runtime; split ONNX выдаёт шесть тензоров регрессии/классов для RKNN. Декодирование DFL на CPU едино для обеих архитектур. Цвет RGB, letterbox с pad 114, ONNX float32 NCHW /255, RKNN uint8 NHWC с нормализацией /255 внутри графа.

Калибровка `pieces2d` использует обрезки, найденные `board2d`, как рабочий каскад. Ненайденные доски перечисляются в `calibration_manifest.json`, без замены полным кадром. Хеши подготовленных пикселей исключают точные совпадения с test; аналогичные кадры и утечку относительно исходного обучения это не исключает.

`02` сравнивает PyTorch, ONNX и split ONNX на test: координаты, вероятности, NMS. `--verification-directory` предназначен для численной проверки на альтернативных кадрах, без утверждения о качестве модели. `06` независимо сверяет letterbox/NMS с Ultralytics, включая разные пропорции кадров.

`04` собирает RKNN и проверяет CPU-симулятор Toolkit2. Критерий: ≥95% precision/recall совпадения с PyTorch при confidence 0,25 и IoU 0,9. Это погрешность конвертации, а не качество по разметке. Код возврата ненулевой при превышении порога; артефакт и отчёт сохраняются. `--algorithm normal|mmse|kl_divergence` выбирает калибровку; MMSE может быть очень длительным. По умолчанию `normal`.

## Проверка расстановки и каскада

Из корня проекта, в окружении `web`:

```bash
web/.venv/bin/python -m vision.evaluate --profile 3d
web/.venv/bin/python -m vision.evaluate --profile 2d
web/.venv/bin/python -m vision.evaluate --backend rknn_fp16 --simulation convert/artifacts/chess3d/rknn_fp16/comparison.json
web/.venv/bin/python -m vision.evaluate --backend rknn_int8 --simulation convert/artifacts/chess3d/rknn_int8/comparison.json
```

3D: совпадение клеток/полной позиции с JSON и отдельная проверка геометрии на эталонных bbox/углах. 2D: полный каскад по меткам Roboflow фигур при IoU 0,5; разметки FEN в этом экспорте нет. Для проверки полного RKNN-каскада нужен настоящий NPU (`--backend rknn_int8`), симуляторные отчёты отдельных 2D-моделей его не заменяют.

Результаты находятся в `artifacts/<model>`; данные и бинарные артефакты игнорируются Git. Фактические результаты: [RUN_REPORT.md](RUN_REPORT.md).
