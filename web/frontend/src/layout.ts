export const layout = `
<header>
  <a class="brand" href="/" aria-label="EdgeChess"><span class="brand-icon">♞</span> EDGE<span>CHESS</span><small>VISION LAB</small></a>
  <div class="header-status"><span class="dot" id="status-dot"></span><span id="status">Подключение…</span><span class="tag" id="backend-tag">ONNX / CPU</span></div>
</header>
<main>
  <section class="intro"><div><h1>Доска в поле зрения</h1><p class="subtitle">Виртуальная партия · распознавание позиции · подсказки Stockfish</p></div><span class="live-badge"><i></i> LIVE INFERENCE</span></section>
  <div class="workspace">
    <section class="board-panel" aria-label="Интерактивная доска">
      <div class="panel-heading"><span><i class="small-dot"></i> Интерактивная сцена</span><span id="turn">Ход белых</span></div>
      <div id="viewport"><canvas id="still-frame" hidden></canvas><canvas id="overlay" aria-label="Рамки распознавания"></canvas><div class="scene-chip">CAM 01 <span>960 × 720</span></div><div id="scene-message" role="status"></div></div>
      <div class="board-toolbar">
        <label class="checkbox"><input id="boxes" type="checkbox" checked><span>Рамки и классы</span></label>
        <button id="home" class="quiet">↺ Сбросить ракурс</button>
        <button id="pause" class="quiet">Приостановить поток</button>
        <span class="toolbar-hint">Потяните для вращения · колесо для масштаба</span>
      </div>
    </section>

    <aside class="live-sidebar" aria-label="Сводка партии">
      <section class="card compact-card" id="performance-card">
        <div class="card-title"><h2>Производительность</h2><span class="tag">5 СЕК</span></div>
        <div class="hero-metric"><strong id="fps">—</strong><span>кадров/с</span><svg id="spark" viewBox="0 0 260 42" preserveAspectRatio="none" aria-hidden="true"><polyline points="" /></svg></div>
        <div class="metric-grid">
          <div><span>Инференс p50</span><strong id="infer">—</strong></div>
          <div><span>Инференс p95</span><strong id="p95">—</strong></div>
          <div><span>Возраст p50</span><strong id="age">—</strong></div>
        </div>
      </section>

      <section class="card compact-card" id="recognition-card">
        <div class="card-title"><h2>Распознавание</h2><span id="recognition-badge" class="status-chip" data-state="neutral">Ожидание</span></div>
        <div class="recognition-value"><strong id="recognition-score">—</strong><span>клеток совпало</span></div>
        <p id="accuracy" role="status">Ожидаем кадр сцены</p>
      </section>

      <section class="card compact-card" id="stockfish-card">
        <div class="card-title"><h2>Stockfish</h2><label class="side-choice">За <select id="advisor-side" aria-label="Сторона помощника"><option value="w">Белых</option><option value="b">Чёрных</option></select></label></div>
        <button id="ask-advice" disabled>Подсказать ход</button>
        <label class="checkbox advisor-check"><input id="advisor-vision" type="checkbox" checked><span>Подтверждать позицию через YOLO</span></label>
        <label class="checkbox advisor-check"><input id="advisor-speech" type="checkbox" checked><span>Озвучивать на Firefly / сервере</span></label>
        <p id="speech-status" class="note" role="status"></p>
        <p id="advice-status" role="status">Синхронизация истории…</p>
        <p id="advice-result" role="status"></p>
        <div class="move-key"><span><i class="from-square"></i> Откуда</span><span><i class="to-square"></i> Куда</span><span>Ход не выполняется</span></div>
      </section>
    </aside>
  </div>

  <div class="controls-grid" aria-label="Позиция и настройки">
    <section class="card position-controls">
      <div class="card-title"><h2>Позиция партии</h2><button id="reset" class="quiet">Начальная позиция</button></div>
      <label class="field-caption" for="fen">FEN виртуальной доски</label>
      <div class="fen-row"><input id="fen" spellcheck="false" aria-label="Позиция FEN"><button id="apply">Применить</button></div>
      <div class="position-actions"><p id="move-help">Нажмите на фигуру, затем на клетку назначения. Вы играете за обе стороны.</p><label>Превращение <select id="promotion"><option value="q">Ферзь</option><option value="r">Ладья</option><option value="b">Слон</option><option value="n">Конь</option></select></label></div>
      <details class="game-details"><summary>История и синхронизация</summary><p id="game-history"></p><p id="advice-meta"></p><button id="sync-game" class="quiet">Повторить синхронизацию</button></details>
    </section>

    <section class="card" id="scene-settings">
      <h2>Настройки сцены</h2>
      <label class="field">Источник <select id="source-mode"><option value="3d">3D-сцена</option><option value="2d">2D-доска</option></select></label>
      <label class="field">Материалы <select id="theme"><option value="wood">Дерево</option><option value="marble">Мрамор</option><option value="walnut">Орех</option></select></label>
      <label class="field">Фигуры 3D <select id="shape"><option value="classic">Классические</option><option value="slim">Узкие</option><option value="glb" disabled>Из GLB</option></select></label>
      <label class="field">Свет <input id="light" type="range" min="1" max="6" step="0.5" value="3.5"></label>
      <label class="field field-stack">Набор фигур GLB <input id="piece-set" type="file" accept=".glb"></label>
      <p class="note">12 объектов wP…wK и bP…bK, ось Y вверх. До 20 MiB.</p>
    </section>

    <section class="card" id="processing-settings">
      <h2>Обработка</h2>
      <label class="field">Пайплайн <select id="profile"><option value="3d">3D · углы и фигуры</option><option value="2d">2D · доска и обрезка</option></select></label>
      <label class="field" id="model-label">Модель 3D <select id="model"></select></label>
      <label class="field">Исполнитель <select id="backend"><option value="onnx">ONNX CPU</option><option value="rknn_fp16">RKNN FP16 · NPU</option><option value="rknn_int8">RKNN INT8 · NPU</option></select></label>
      <label class="field">Ориентация 2D <select id="orientation"><option value="white">Белые снизу</option><option value="black">Чёрные снизу</option></select></label>
      <label class="field">Частота захвата <select id="capture-fps"><option value="10">10 FPS</option><option value="15">15 FPS</option><option value="30" selected>30 FPS</option><option value="60">60 FPS</option></select></label>
    </section>

    <section class="card" id="frame-tools">
      <h2>Снимки и проверка JPEG</h2>
      <button id="save-frame" class="quiet wide-button">↓ Сохранить кадр сцены</button>
      <label class="field field-stack">Загрузить JPEG <input id="image-file" type="file" accept="image/jpeg"></label>
      <button id="analyze" class="quiet wide-button">Проверить выбранный кадр</button>
      <p class="note">Перед анализом файла приостановите поток. Загруженный кадр не подтверждает виртуальную партию.</p>
    </section>

    <section class="card recognition-details">
      <details><summary>Детали распознавания <span id="detection-count" class="count">0</span></summary>
        <p id="vision-status">Ожидаем кадр</p><code id="recognized-placement"></code>
        <div class="recognition-fields">
          <label class="field field-stack">Чей ход <select id="active-color"><option value="w">Белые</option><option value="b">Чёрные</option></select></label>
          <label class="field field-stack">Рокировка <input id="castling" value="-" maxlength="4"></label>
          <label class="field field-stack">Взятие на проходе <input id="en-passant" value="-" maxlength="2"></label>
        </div>
        <p id="recognized-fen"></p><p class="note">Расстановка — результат сети. Остальные поля задаются вручную; счётчики — 0 и 1.</p>
        <div class="table-heading"><span>КЛАСС</span><span>CONFIDENCE</span></div><div id="detections"><p class="empty">Ожидаем результат модели</p></div>
      </details>
    </section>

    <section class="card model-card">
      <details><summary>Модель и подробные метрики</summary>
        <strong id="model-name">Загрузка модели…</strong><p id="model-info">Прогрев перед замерами</p>
        <div class="timing-list">
          <div><span>Возраст кадра · p95</span><b id="age95">—</b></div>
          <div><span>Подготовка / NMS</span><b id="stages">—</b></div>
          <div><span>Ожидание обработки</span><b id="queue">—</b></div>
          <div><span>Отправлено / заменено</span><b id="counts">0 / 0</b></div>
          <div><span>Пропущено до отправки</span><b id="skipped">0</b></div>
          <div><span>Отрисовка / захват, FPS</span><b id="render-fps">—</b></div>
        </div>
        <div class="export-row"><button id="json" class="quiet">↓ JSON</button><button id="csv" class="quiet">↓ CSV</button></div>
        <p class="note">Экспорт метрик последних 5 минут. Свежие кадры заменяют ожидающие; рамки могут отставать при движении.</p>
      </details>
    </section>
  </div>
  <footer><span>EDGECHESS / VIRTUAL CAMERA</span><span>YOLO · STOCKFISH · ONNX / RKNN</span></footer>
</main>`;
