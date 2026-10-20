# Развёртывание на Firefly

Для голосовых подсказок см. [Piper TTS](tts.md): импорт модели, флаг упаковки
`--with-tts`, установка aplay в conda и выбор аналогового аудиовыхода.

## Требования

- Linux ARM64, glibc ≥ 2.35 для официального Stockfish 19.
- Conda с Python 3.10–3.12, доступ к Python-индексу для установки зависимостей.
- RKNN Lite2 2.3.2 и совместимые драйвер NPU / `librknnrt`.
- Свободное место для архива, распакованного приложения и conda-окружения.

Версию glibc проверьте командой `getconf GNU_LIBC_VERSION`. Для более старой
ОС требуется совместимая сборка Stockfish из приложенных исходников;
conda не заменяет системную glibc.

## Сборка пакета

На локальной машине, из корня репозитория:

```bash
python3 tools/download_stockfish.py --arch aarch64
npm --prefix web/frontend ci
npm --prefix web/frontend run build
python3 tools/package_firefly.py --profiles 3d --3d-models chess3d_m \
  --backends rknn_int8 rknn_fp16 --output artifacts/firefly-stockfish.tar
```

Требуются [подготовленные RKNN и metadata](models.md). Архив включает
runtime, frontend, ARM64 Stockfish, исходники/GPL и зависимости из `web/uv.lock`.
Рядом записывается файл `.sha256`.

Для обновления с сохранением моделей существующей установки:

```bash
python3 tools/package_firefly.py --profiles 3d --3d-models chess3d_m \
  --backends rknn_int8 rknn_fp16 --reuse-artifacts \
  --output artifacts/firefly-stockfish-overlay.tar
```

Пакет `overlay` **не содержит YOLO-моделей**. Профили, модели и исполнители
перечислены в `PACKAGE.json`; `external_yolo_artifacts_required: true`
означает, что их нужно перенести из существующей установки.

## Установка

Скопируйте архив и `.sha256` на плату. Задайте абсолютные пути:
`APP_DIR` — новый каталог приложения, `ARCHIVE` — архив.

```bash
cd "$(dirname "$ARCHIVE")"
sha256sum -c "$(basename "$ARCHIVE").sha256"
mkdir -p "$APP_DIR"
tar -xf "$ARCHIVE" -C "$APP_DIR"
```

Только для `overlay`: задайте `OLD_APP_DIR` и перенесите модели:

```bash
mkdir -p "$APP_DIR/convert/artifacts"
cp -a "$OLD_APP_DIR/convert/artifacts/chess3d_m" "$APP_DIR/convert/artifacts/"
```

Установите зависимости в отдельную conda:

```bash
conda create --prefix "$APP_DIR/.conda" python=3.10 pip -y
conda activate "$APP_DIR/.conda"
cd "$APP_DIR"
bash tools/install_firefly.sh
bash tools/run_firefly.sh
```

Установщик проверяет архитектуру, glibc, SHA256 и UCI-запуск Stockfish.
Python-пакеты и бинарник устанавливаются в активную conda. Исходники и GPL
сохраняются в `$CONDA_PREFIX/share/edgechess-stockfish`.

## Подключение и проверка

Сервер по умолчанию слушает `127.0.0.1:8000`. На компьютере с браузером:

```bash
ssh -N -L 18000:127.0.0.1:8000 "$EDGECHESS_SSH_ALIAS"
```

Откройте `http://localhost:18000`. В `/api/health` проверьте
`provider: RKNN NPU`, `backend: rknn_int8` и `stockfish.available: true`.
Затем проверьте поток распознавания и подсказку по кнопке.

Для запуска с FP16: `EDGECHESS_BACKEND=rknn_fp16 bash tools/run_firefly.sh`.
Настройки сети: `EDGECHESS_BIND_HOST`, `EDGECHESS_PORT`. Публичный доступ
без внешней аутентификации не предусмотрен.
