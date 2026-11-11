# Firefly: развёртывание с нуля

## Что взять на сдачу

Из `artifacts/`: **`edgechess-firefly-latest.tar.gz` и одноимённый `.sha256`**.
Архив самодостаточный: Python 3.10.21 ARM64, закреплённые Python-зависимости,
YOLOv8m RKNN INT8/FP16, интерфейс, Stockfish 19 с исходниками/GPL, голос Piper.
Git, Node.js, conda, pip и интернет на плате для установки приложения не нужны.
Архив не содержит ОС и драйвер ядра NPU. Обучение и датасеты в него не входят.

## Требования к новой плате

- Firefly **RK3588S/RK3588**, Linux ARM64, **glibc ≥ 2.35** (Ubuntu 22.04/24.04).
- Рабочий драйвер Rockchip NPU и совместимая с RKNN Lite2 **2.3.2**
  `librknnrt.so` — заранее подготовленный образ Firefly/Rockchip. Проверка ниже
  реально загружает модель на NPU; запуск только на CPU не подменяет её.
- ALSA и `aplay` (`alsa-utils`), доступ пользователя к аудио/NPU, подключённые
  активные колонки/наушники. Если `aplay` отсутствует, администратор устанавливает
  `alsa-utils` заранее; приложение системные пакеты и настройки не меняет.
- **Не менее 2 ГБ свободного места** под архив, распаковку и запас; около 2 ГБ
  доступной RAM. Сеть между платой и компьютером с браузером, SSH-доступ.

## Установка и запуск

На компьютере, из корня репозитория; замените `USER`, `IP` и разрешённый каталог:

```bash
scp artifacts/edgechess-firefly-latest.tar.gz* USER@IP:/РАЗРЕШЁННЫЙ/КАТАЛОГ/
ssh USER@IP
```

На плате (распаковывайте **в новый каталог**, не поверх работающей версии):

```bash
cd /РАЗРЕШЁННЫЙ/КАТАЛОГ
uname -m                       # aarch64
getconf GNU_LIBC_VERSION        # glibc 2.35 или новее
df -h .
sha256sum -c edgechess-firefly-latest.tar.gz.sha256
mkdir edgechess
tar -xzf edgechess-firefly-latest.tar.gz -C edgechess
cd edgechess
bash edgechess.sh check --audio # файлы → NPU → Stockfish → Piper → звук
bash edgechess.sh start         # фон, переживает закрытие SSH; НЕ перезагрузку
bash edgechess.sh status
```

На компьютере откройте туннель (оставьте команду работающей):

```bash
ssh -N -L 18000:127.0.0.1:8000 USER@IP
```

Откройте **http://localhost:18000**. В интерфейсе: `3D`, `YOLOv8m`, `RKNN INT8`.
Дождитесь подтверждения начальной позиции и нажмите «Подсказать ход».
Ход подсветится, но не выполнится; голос звучит **на плате**, не в браузере.
В `/api/health`: `provider: RKNN NPU`, `backend: rknn_int8`,
`stockfish.available: true`, `speech.available: true`.

## Управление и неполадки

```bash
bash edgechess.sh stop
bash edgechess.sh start
tail -n 80 web-ui.log
```

- Для FP16: после остановки `EDGECHESS_BACKEND=rknn_fp16 bash edgechess.sh start`.
- Другой порт: `EDGECHESS_PORT=8001 bash edgechess.sh start`; тот же параметр
  указывайте для `status`, порт туннеля справа тоже замените на `8001`.
- Прямой доступ: `EDGECHESS_BIND_HOST=IP_ПЛАТЫ bash edgechess.sh start`.
  По умолчанию только localhost; **аутентификации нет**, не публикуйте в интернете.
- Ошибка NPU: проверить образ ОС, драйвер, `librknnrt.so`, права доступа.
  Автоматического перехода на CPU нет. Статическое предупреждение
  `Query dynamic range failed` само по себе не означает ошибку инференса.
- Нет звука: `aplay -l`, `aplay -L`, проверить колонки, громкость/mute в микшере.
  Для ES8388 автоматически используется локальный `audio.conf`: стерео 48 кГц,
  амплитуда 20%; системный микшер не меняется. На другой плате задайте, например,
  `EDGECHESS_AUDIO_DEVICE=default bash edgechess.sh start` после остановки.
  Успех `aplay` ещё не доказывает физическую слышимость. Подробнее: [tts.md](tts.md).
- Сервер занят: закрыть вкладки с распознаванием; допускается один поток.
- После перезагрузки снова выполните `bash edgechess.sh start` из этой папки.

Всё приложение пишет только внутри своей папки. Старую установку/архив можно
удалить после проверки новой; `stockfish/upstream.tar.gz` внутри приложения
сохраните — это исходники и лицензии. Голос Piper имеет неуточнённые права на
исходный датасет: архив не следует публично распространять без проверки лицензии.

## Пересборка на компьютере

Нужны Linux x86_64, `uv`, Python 3, Node.js 22/npm и интернет. Подготовленные
модели должны быть в `convert/artifacts/chess3d_m/` ([models.md](models.md)).

```bash
npm --prefix web/frontend ci
npm --prefix web/frontend run build
python3 tools/package_firefly_release.py
```

Сборщик сам скачивает Python, ARM64-зависимости, Stockfish и голос; входные
загрузки кэшируются в `.cache/firefly-release/`. В `artifacts/` создаются только
актуальный архив и checksum. На новую плату исходный репозиторий не нужен.
