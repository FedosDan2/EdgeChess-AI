# Генерация синтетического датасета

## Запуск

Требуются Node.js 22, npm и Chromium для Playwright. Из корня репозитория:

```bash
cd web/frontend
npm ci
npx playwright install chromium
npm run dataset
```

Для системных зависимостей Chromium в Linux используйте
`npx playwright install-deps chromium`.

По умолчанию: `data/synthetic-demo`, 24 позиции × 2 ракурса, 640×640, seed 42.
Настраиваемый запуск:

```bash
npm run dataset -- --output ../../data/synthetic-2000 --positions 1000 --views 2 --size 640 --seed 42
```

Для собственного набора фигур добавьте `--glb /path/pieces.glb`.
Имена объектов: `wP wN wB wR wQ wK bP bN bB bR bQ bK`, ось Y вверх.
Существующий каталог не перезаписывается.

## Формат

Выход: `data.yaml`, `manifest.json` и `train/val/test`, в каждом —
`images/`, `labels/`, `masks/`, `metadata/`.

- YOLO: `class cx cy width height`, нормированные координаты.
- 16 классов: 12 сочетаний цвета/фигуры и 4 угла доски.
- Углы `white_left`, `white_right`, `black_left`, `black_right` соответствуют
  a1, h1, h8, a8; bbox угла — 5% стороны изображения.
- Bbox фигур строятся по видимым пикселям с учётом перекрытий.
  Полностью невидимые фигуры записываются в `hiddenSquares`, без bbox.
- Маска RGB: красный канал — instance ID, 0 — фон.
- Metadata содержит FEN, геометрию, освещение, углы, bbox и параметры кадра.

Позиции генерируются легальными ходами. Разделение 80/10/10 — по уникальной
расстановке; все её ракурсы принадлежат одному split. Геометрия соответствует
сцене UI и не заменяет независимую выборку для оценки качества модели.
