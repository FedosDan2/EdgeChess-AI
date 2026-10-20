# EdgeChess AI

Шахматный помощник: виртуальная 2D/3D-доска, распознавание YOLO, подсказки
Stockfish по запросу. ONNX выполняется на CPU, RKNN — на NPU Firefly RK3588S.
Локальный Piper TTS озвучивает рекомендованный ход через аудиовыход сервера.

## Документация

- [Локальный запуск и управление](docs/local.md)
- [Установка на Firefly](docs/firefly.md)
- [Stockfish и история партии](docs/stockfish.md)
- [Озвучка Piper TTS](docs/tts.md)
- [Конвертация моделей](docs/models.md)
- [Генерация датасета](docs/dataset.md)
- [Подготовка данных и обучение](docs/training.md)
- [Тестирование](docs/testing.md)

## Компоненты

| Каталог | Назначение |
|---|---|
| `vision/` | Инференс, геометрия доски, распознавание расстановки |
| `convert/` | Экспорт ONNX, калибровка и сборка RKNN |
| `web/` | FastAPI, виртуальная доска, Stockfish |
| `CV_2D/`, `CV_3D/` | Веса и обучение моделей |
| `tools/` | Загрузка Stockfish, упаковка и запуск Firefly |
