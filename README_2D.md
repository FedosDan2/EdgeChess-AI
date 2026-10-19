# Обучение 2D-моделей

Для распознавания и запуска web-ui используйте общий runtime `vision`:
[инструкция запуска](web/README.md). Старый `CV_2D/main.py` и дублирующий
пайплайн не включены в объединённую версию.

## Подготовка данных

Подготовка данных выполняется отдельно от минимального NPU-runtime.
Скрипту нужны Python, `pyyaml` и `tqdm`; для обучения — Ultralytics и
совместимое окружение PyTorch. Версии исходного обучающего окружения
в ветке `cv` не были зафиксированы.

Скачайте YOLOv8-экспорты Roboflow:

- [Доска](https://universe.roboflow.com/devil3515/chessboard-detection-loqg5).
- [Фигуры](https://universe.roboflow.com/chess-raa7q/chess-cfal9).

Распакуйте их в `CV_2D/data/dirty_data/board` и
`CV_2D/data/dirty_data/board_and_pieces`, затем из корня репозитория выполните:

```bash
python setup_dataset_2d.py
```

Скрипт переименует split `valid` в `val`, сдвинет IDs классов фигур на +1
и создаст `CV_2D/data/clean_data/board_dataset/data.yaml` и
`CV_2D/data/clean_data/pieces_dataset/data.yaml`. Он ожидает исходный порядок
12 классов фигур из указанного экспорта; перед обучением проверьте его.
Команды обучения двух моделей печатаются после успешной подготовки.

## Веса и инференс

- `CV_2D/weights/best_board_detect.pt` — детектор доски (`board2d`).
- `CV_2D/weights/best_board_and_pieces.pt` — детектор фигур (`pieces2d`).

Экспорт и калибровка: [convert/README.md](convert/README.md).
Профиль `2d` в `vision` использует каскад «доска → обрезка → фигуры → клетки».
