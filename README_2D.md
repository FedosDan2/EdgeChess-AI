
# README_2D.md

```markdown
# 2D Chess Pipeline (Screenshots)

Две модели YOLO: доска (1 класс) + фигуры (13 классов, chessboard=0, фигуры=1-12).

## Установка

```bash
pip install opencv-python pyyaml tqdm ultralytics
```
## Веса
Веса моделей лежат в `./EdgeChess-AI/CV_2D/weights`
`EdgeChess-AI/CV_2D/weights/best_board_and_pieces.pt` - веса для модели детекции фигур
`EdgeChess-AI/CV_2D/weights/best_board_detect.pt` - веса для модели детекции доски

## Подготовка датасетов

1. Скачай с Roboflow (YOLOv8 формат):
   - [Доска](https://universe.roboflow.com/devil3515/chessboard-detection-loqg5)
   - [Фигуры](https://universe.roboflow.com/chess-raa7q/chess-cfal9)

2. Распакуй в:
```
EdgeChess-AI/CV_2D/data/dirty_data/
├── board/
└── board_and_pieces/
```

3. Запусти:
```bash
python setup_dataset_2d.py
```
Сдвинет классы фигур на +1, создаст `clean_data/board_dataset/` и `clean_data/pieces_dataset/`.

## Инференс
```bash
cd CV_2D
python main.py
```


**Ключевые отличия от 3D:**
- Нет Perspective Transform (доска уже сверху).
- Две модели вместо одной.
- Координаты фигур считаются относительно bbox доски, а не через матрицу трансформации.

**Результат:** FEN-строка позиции.
```