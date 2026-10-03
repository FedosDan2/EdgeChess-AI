# README_3D.md

```markdown
# 3D Chess Pipeline (ChessRender360)

Детекция доски + углов + фигур на 3D-рендерах → Perspective Transform → FEN.

## Установка

```bash
pip install kaggle albumentations opencv-python pyyaml tqdm ultralytics
```

## Веса
Веса моделей лежат в `./EdgeChess-AI/CV_3D/weights`
`EdgeChess-AI/CV_3D/weights/best_3d_detection.pt` - веса для модели детекции 


## Подготовка датасета

```bash
python setup_dataset_3d.py
```
Скачает ~26GB, применит аугментации (2 копии на train), создаст `./yolo_chess_dataset/data.yaml` (16 классов: 12 фигур + 4 угла).

## Инференс

```bash
cd CV_3D
python main.py
```

**Пайплайн:**
1. `BoardDetector` → находит 4 угла (классы 12-15).
2. `BoardTransformer` → Perspective Transform по углам (доска → вид сверху 900x900).
3. `PiecesDetector` → детектит фигуры на исходном изображении.
4. `PieceMapper` → переносит фигуры на выпрямленную доску (точка основания bbox + смещение на 40% высоты).
5. `SquareMapper` → пиксели → клетка (e4).
6. `BoardState` + `FENBuilder` → матрица 8x8 → FEN-строка.

**Результат:** `results/warped_board.jpg` + `results/fen.txt`.

---
