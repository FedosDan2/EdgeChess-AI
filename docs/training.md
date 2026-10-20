# Подготовка данных и обучение

Требуется отдельное окружение Ultralytics/PyTorch; для обучения — GPU.
Версии обучающих зависимостей не закреплены. Инференс и конвертация используют
свои окружения: [локальный запуск](local.md), [конвертация](models.md).

## 2D

Скачайте YOLOv8-экспорты Roboflow:

- [Доска](https://universe.roboflow.com/devil3515/chessboard-detection-loqg5)
  → `CV_2D/data/dirty_data/board/`.
- [Фигуры](https://universe.roboflow.com/chess-raa7q/chess-cfal9)
  → `CV_2D/data/dirty_data/board_and_pieces/`.

Установите `pyyaml`, `tqdm` и выполните из корня:

```bash
python setup_dataset_2d.py
```

Скрипт создаёт `CV_2D/data/clean_data/{board_dataset,pieces_dataset}/data.yaml`
и печатает команды обучения. Перед запуском проверьте порядок 12 классов
фигур: скрипт сдвигает исходные IDs на +1. `valid` переименовывается в `val`.

## 3D

Данные: [генератор сцены](dataset.md) либо ChessRender360 через
`setup_dataset_3d.py` (около 26 GB; зависимости `kagglehub`, `albumentations`,
`opencv-python`, `numpy`, `pyyaml`, `tqdm`).

**Перед использованием `setup_dataset_3d.py` исправьте применение случайных
аугментаций к `original`, `val` и `test`**, а также настройте `OUTPUT_PATH`.
Независимая валидация должна использовать неизменённые отложенные данные.

Настройте пути `DATA_YAML`, `PROJECT`, веса и `DEVICE`. Из корня выполните
команду для нужного режима:

```bash
python CV_3D/train_3d.py   # обучение от COCO-предобученной YOLOv8m
python CV_3D/fine_tune.py  # дообучение существующей модели
```

Порядок 16 классов должен совпадать с checkpoint. IDs 12–15:
`corner_white_left`, `corner_white_right`, `corner_black_left`, `corner_black_right`.
Активные веса: `best_new_scratch.pt` для `chess3d_m`,
`best_3d_detection.pt` для `chess3d`. Загружайте `.pt` только из доверенных источников.
