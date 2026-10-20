# Тестирование

Команды выполняются из корня репозитория.

## Unit-тесты и сборка

```bash
uv sync --project web --locked
STOCKFISH_PATH="$PWD/artifacts/stockfish/x86_64/stockfish" \
  uv run --project web --locked pytest web/tests -q
npm --prefix web/frontend ci
npm --prefix web/frontend test
npm --prefix web/frontend run build
```

Для теста реального движка предварительно [скачайте Stockfish](local.md).
Без `STOCKFISH_PATH` этот тест пропускается. Тесты ONNX требуют
[экспортированных моделей](models.md).

## Браузерные тесты

```bash
cd web/frontend
npx playwright install chromium
EDGECHESS_WEB_URL=http://127.0.0.1:8000 npm run test:browser
EDGECHESS_WEB_URL=http://127.0.0.1:8000 npm run test:advisor
npm run test:layout
npm run test:dataset
npm run test:highlight
```

Для `test:browser` и `test:advisor` запустите [сервер](local.md).
`test:advisor` требует настоящие YOLOv8m ONNX и Stockfish, а также совпадение
распознанной стартовой позиции с доской. `test:dataset`, `test:highlight` и
`test:layout` запускают сервер самостоятельно. `test:layout` проверяет
адаптивную компоновку и статусы распознавания на фиксированных данных.
`test:highlight` проверяет подсветку 2D/3D,
сброс после хода, отсутствие мерцания при захвате и исключение отметок из входа YOLO.
`test:models` дополнительно требует экспорта обеих 3D-моделей и 2D-каскада.

## Измерения

```bash
uv run --project web --locked python -m web.backend.benchmark \
  --profile 3d --backend onnx --runs 100 /path/frame.jpg
STOCKFISH_PATH="$PWD/artifacts/stockfish/x86_64/stockfish" \
  web/.venv/bin/python tools/experiment_stockfish.py /path/frame.jpg --runs 10
```

Бенчмарк измеряет preprocessing, модель, NMS и геометрию, без сети/JPEG/отрисовки.
Эксперимент запускает CPU YOLO и Stockfish совместно; JSON сохраняется в `artifacts/`.
Тесты `web/tests/test_speech.py` проверяют текст ходов, отмену синтеза/проигрывания,
ограниченную очередь и сохранение подсказки при ошибке аудио. После импорта
голоса и установки extra `tts` запуск с `STOCKFISH_PATH` также проверяет
настоящие Stockfish + Piper и структуру полученного WAV (без физического звука).

```bash
STOCKFISH_PATH=/путь/к/stockfish uv run --project web --extra tts --locked pytest web/tests/test_speech.py -q
```

Эти измерения не заменяют проверку задержек, RAM и температуры на Firefly.
