# Stockfish: виртуальная партия и Firefly

Ветка `feat/stockfish` добавляет подсказку **только по кнопке** за выбранную
сторону. Ход не выполняется автоматически. Поддерживаются стандартная позиция
и загрузка произвольного допустимого FEN. TTS и воспроизведение на динамике
в этот этап не входят.

## Как работает

`chess.js` передаёт начальный FEN и историю UCI в `POST /api/game`.
Сервер воспроизводит легальные ходы через `chess==1.11.2`; сохраняются очередь
хода, права рокировки, en passant, счётчики и история повторений. Загрузка FEN
начинает новую историю; восстановить более ранние повторения из FEN нельзя.
Сессии в памяти (до 32), исчезают после перезапуска. При необходимости нажмите
«Повторить синхронизацию». Перезагрузка страницы начинает новую партию.

История **не передаётся в YOLO** и не корректирует его результат. По умолчанию
подсказка требует два последовательных совпадения распознанной расстановки
с историей, `status=ok`, без предупреждений. Последнее совпадение должно быть
не старше трёх секунд от приёма кадра сервером. Это защита интерфейса, а не
метрика точности детектора. Пропущенные углы, конфликты клеток или неверные
фигуры блокируют подсказку, а не заменяются эталонной сценой.

Флажок «Требовать совпадения с YOLO» можно явно отключить для диагностики
Stockfish. UI и API тогда маркируют результат как **только история UI**.
Это не успешная проверка распознавания. Отдельный загруженный JPEG не является
подтверждением виртуальной партии.

`POST /api/advice` принимает `game_id`, `revision`, `require_vision` (по умолчанию
`true`). Отказ при чужом ходе, завершённой партии, неподтверждённой позиции,
устаревшей версии или занятом движке — HTTP 409. Ошибка движка — HTTP 503,
не останавливает YOLO. Нет неограниченной очереди: только один расчёт.
Устаревший результат отбрасывается и на сервере, и в браузере.

Stockfish — отдельный постоянный CPU-процесс и отдельный executor, не
inference-worker. По умолчанию поиск 1 секунда, 1 поток, Hash 64 MiB:

```bash
export EDGECHESS_STOCKFISH_SECONDS=1   # 0.05..10
export EDGECHESS_STOCKFISH_THREADS=1   # 1..4
export EDGECHESS_STOCKFISH_HASH_MB=64  # 1..256
```

Изменения применяются после перезапуска сервера. Конкуренция за CPU/RAM с
pre/postprocessing YOLO остаётся даже при инференсе на NPU.

## Локальный запуск на CPU

Скачивается закреплённый **официальный Stockfish 19**, с проверкой SHA256.
Windows-бинарник из архива коллеги не используется. Загрузчик хранит исходный
архив поставки с исходниками и GPL-уведомлениями рядом с бинарником.

Из корня репозитория на Linux x86_64:

```bash
python3 tools/download_stockfish.py --arch x86_64
npm --prefix web/frontend ci
npm --prefix web/frontend run build
cd web
uv sync --locked
STOCKFISH_PATH="$PWD/../artifacts/stockfish/x86_64/stockfish" \
EDGECHESS_PROFILE=3d EDGECHESS_3D_MODEL=chess3d_m EDGECHESS_BACKEND=onnx \
uv run --locked uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Для настоящего YOLO нужны `convert/artifacts/chess3d_m/model.onnx` и
`model.json`, подготовленные по [инструкции конвертации](convert/README.md).
Без модели YOLO сервер не запускается; фиктивных детекций в runtime нет.
Отсутствие Stockfish не мешает запуску YOLO: UI покажет недоступность подсказки.

Тест реального движка:

```bash
cd web
STOCKFISH_PATH="$PWD/../artifacts/stockfish/x86_64/stockfish" uv run --locked pytest -q
```

## Подготовка архива для Firefly (локально)

```bash
python3 tools/download_stockfish.py --arch aarch64
npm --prefix web/frontend run build
python3 tools/package_firefly.py --profiles 3d --3d-models chess3d_m \
  --backends rknn_int8 rknn_fp16 --output artifacts/firefly-stockfish.tar
```

Полная поставка включает RKNN, metadata, frontend, backend, ARM64 Stockfish,
исходную поставку Stockfish/GPL, requirements из lock-файла и скрипты conda.
Если артефакты отсутствуют локально, команда завершается ошибкой, без тихого
пропуска моделей.

Рядом с архивом записывается `.sha256`. После копирования выполните
`sha256sum -c firefly-stockfish.tar.sha256` (для overlay — его имя файла).

Для обновления **уже установленного** YOLO-runtime есть явный вариант:

```bash
python3 tools/package_firefly.py --profiles 3d --3d-models chess3d_m \
  --backends rknn_int8 rknn_fp16 --reuse-artifacts \
  --output artifacts/firefly-stockfish-overlay.tar
```

Это **не автономный пакет моделей**: `PACKAGE.json` содержит
`external_yolo_artifacts_required: true`. Он включает новый код, frontend и
Stockfish, но требует переноса существующего `convert/artifacts/chess3d_m`
с платы (оба RKNN-backend и metadata). Старые артефакты проверяются существующим
загрузчиком по SHA256. Нет датасетов, PT, TTS, venv, паролей или `.env`.

## Установка на Firefly: только внутри conda

Плата сейчас недоступна: ARM64-поставка подготовлена, но её запуск, драйвер
RKNN и одновременная нагрузка **ещё должны быть проверены на устройстве**.
Интернет нужен для pip-зависимостей. Сам Stockfish уже находится в архиве.
Официальный Linux Stockfish 19 требует **glibc ≥ 2.35** (например, Ubuntu
22.04+). Проверьте `getconf GNU_LIBC_VERSION`. Conda не обновляет системную
glibc. На более старой ОС установщик остановится до установки пакетов:
потребуется сборка из приложенных исходников под эту ОС; её нельзя считать
проверенной без доступа к плате. При успешной установке выполняется реальный
короткий UCI-поиск и проверка легальности ответа.

1. Проверьте RAM и место (архив содержит также полную исходную поставку
   Stockfish). Ничего не удаляйте и не останавливайте чужие процессы.
2. Скопируйте архив в согласованную папку и распакуйте в **новый** `APP_DIR`,
   не поверх чужого приложения. Например: `tar -xf /path/to/archive.tar -C "$APP_DIR"`.
3. Для overlay скопируйте существующие артефакты из старой установки:

```bash
mkdir -p "$APP_DIR/convert/artifacts"
cp -a "$OLD_APP_DIR/convert/artifacts/chess3d_m" "$APP_DIR/convert/artifacts/"
```

4. Создайте отдельное conda-окружение **внутри рабочей папки**:

```bash
conda create --prefix "$APP_DIR/.conda" python=3.10 pip -y
conda activate "$APP_DIR/.conda"
cd "$APP_DIR"
bash tools/install_firefly.sh
bash tools/run_firefly.sh
```

Python-пакеты устанавливаются `python -m pip` именно активной conda; бинарник
Stockfish — в `$CONDA_PREFIX/bin`, исходники/GPL — в
`$CONDA_PREFIX/share/edgechess-stockfish`. Системный Python и старое conda-
окружение не меняются. Чужой Stockfish скрипт не перезаписывает.

По умолчанию сервер слушает `127.0.0.1:8000`; используйте SSH-туннель:

```bash
ssh -N -L 18000:127.0.0.1:8000 "$EDGECHESS_SSH_ALIAS"
```

Откройте `http://localhost:18000`. Для доступа по своей доверенной сети задайте
`EDGECHESS_BIND_HOST`; публичная публикация и аутентификация не настроены.
В `/api/health` должны быть `provider: RKNN NPU` и
`stockfish.available: true`. Импорт RKNN недостаточен — проверьте настоящий поток.

### Приёмка на плате

- Стандартная позиция и произвольный FEN; несколько ходов обеих сторон.
- Кнопка недоступна на чужом ходе и при мате/ничьей.
- Корректные рокировка, en passant и превращение; рекомендация не делает ход.
- Отказ при несовпадении YOLO, явное обозначение режима без проверки YOLO.
- Изменение позиции во время поиска не показывает старую подсказку.
- Сравнить FPS/p50/p95 YOLO до поиска и во время запросов, RAM и температуру.
- Проверить перезапуск, освобождение Stockfish и отсутствие лишних процессов.

Stockfish и библиотека `chess` распространяются под GPL. При передаче пакета
сохраняйте исходники и лицензионные уведомления. Голос Piper и код TTS из
архива коллеги в эту поставку не включены.

Результаты локальной проверки: [web/STOCKFISH_REPORT.md](web/STOCKFISH_REPORT.md).
