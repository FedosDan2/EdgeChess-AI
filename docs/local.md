# Локальный запуск

## Требования

- Linux x86_64, uv, Node.js 22 и npm.
- Экспортированная модель: `convert/artifacts/chess3d_m/model.onnx` и
  `model.json`. Подготовка: [конвертация моделей](models.md).
- Для официального Stockfish 19 — glibc ≥ 2.35.

Команды выполняются из корня репозитория:

```bash
python3 tools/download_stockfish.py --arch x86_64
npm --prefix web/frontend ci
npm --prefix web/frontend run build
uv sync --project web --locked
STOCKFISH_PATH="$PWD/artifacts/stockfish/x86_64/stockfish" \
EDGECHESS_PROFILE=3d EDGECHESS_3D_MODEL=chess3d_m EDGECHESS_BACKEND=onnx \
uv run --project web --locked uvicorn web.backend.app:app --host 127.0.0.1 --port 8000
```

Откройте `http://127.0.0.1:8000`. Без Stockfish распознавание остаётся доступным.

## Управление

Сводка производительности, распознавания и Stockfish находится справа от доски.
Позиция и настройки — под доской; технические данные раскрываются отдельно.

- Для хода нажмите фигуру, затем целевую клетку. Играть можно за обе стороны.
- «Применить» загружает FEN и начинает новую историю; «Начальная позиция» сбрасывает партию.
- Перетаскивание вращает 3D-доску, колесо меняет масштаб; «Сбросить ракурс» восстанавливает камеру.
- Выберите сторону помощника и нажмите «Подсказать ход». Исходная клетка
  подсвечивается синим, целевая — зелёным. Ход не выполняется автоматически.
- Подсветка сбрасывается после хода, загрузки FEN и изменения настроек помощника.
- «Рамки и классы» управляет отображением детекций, а не распознаванием.
- Для анализа отдельного JPEG приостановите поток и выберите файл.
- JSON/CSV экспортирует метрики последних пяти минут; p50/p95 в UI — за последние пять секунд.

Источник сцены и профиль распознавания выбираются независимо. 2D использует
каскад `board2d → pieces2d`; 3D — `chess3d_m` или `chess3d`.
Переключение на CPU при ошибке NPU автоматически не выполняется.

## Настройки сервера

| Переменная | Значение по умолчанию / варианты |
|---|---|
| `EDGECHESS_PROFILE` | `3d`; `2d`, `3d` |
| `EDGECHESS_3D_MODEL` | `chess3d_m`; `chess3d_m`, `chess3d` |
| `EDGECHESS_BACKEND` | `onnx`; `onnx`, `rknn_fp16`, `rknn_int8` |
| `EDGECHESS_ARTIFACTS` | `convert/artifacts` |
| `EDGECHESS_THREADS` | `4` |
| `EDGECHESS_CONFIDENCE` | `0.5` |

GLB-набор должен содержать объекты `wP wN wB wR wQ wK bP bN bB bR bQ bK`,
ось Y вверх; максимальный размер — 20 MiB.
SVG-фигуры cburnett: [CC BY-SA 3.0](../web/frontend/public/pieces/cburnett/LICENSE.md).
