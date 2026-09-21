import "./style.css";
import { BoardScene } from "./scene";
import { percentile, scaleBox } from "./metrics.mjs";
import type { PieceSymbol } from "chess.js";

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <header><a class="brand" href="/" aria-label="EdgeChess"><span class="brand-icon">♞</span> EDGE<span>CHESS</span><small>VISION LAB</small></a><div class="header-status"><span class="dot" id="status-dot"></span><span id="status">Подключение…</span><span class="tag">ONNX / CPU</span></div></header>
  <main><section class="intro"><div><p class="eyebrow">ВИРТУАЛЬНАЯ КАМЕРА · 01</p><h1>Доска в поле зрения.</h1><p class="subtitle">Меняйте позицию и ракурс. Наблюдайте за распознаванием в реальном времени.</p></div><span class="live-badge"><i></i> LIVE INFERENCE</span></section>
  <div class="workspace"><section class="board-panel"><div class="panel-heading"><span><i class="small-dot"></i> Интерактивная сцена</span><span id="turn">Ход белых</span></div><div id="viewport"><canvas id="overlay" aria-label="Рамки распознавания"></canvas><div class="scene-chip">CAM 01 <span>960 × 720</span></div><div id="scene-message" role="status"></div></div><div class="board-toolbar"><label class="checkbox"><input id="boxes" type="checkbox" checked><span>Рамки и классы</span></label><button id="home" class="quiet">↺ Ракурс</button><span class="toolbar-hint">Потяните для вращения · колесо для масштаба</span></div><div class="position"><label for="fen">ПОЗИЦИЯ / FEN</label><div class="fen-row"><input id="fen" spellcheck="false" aria-label="Позиция FEN"><button id="apply">Применить</button></div><div class="position-actions"><button id="reset" class="quiet">Начальная позиция</button><label>Превращение пешки <select id="promotion"><option value="q">Ферзь</option><option value="r">Ладья</option><option value="b">Слон</option><option value="n">Конь</option></select></label></div><p id="move-help">Нажмите на фигуру, затем на клетку назначения. Вы играете за обе стороны.</p></div></section>
  <aside><section class="card"><div class="card-title"><h2>Производительность</h2><span class="tag">LIVE</span></div><div class="hero-metric"><strong id="fps">—</strong><span>кадров/с<br><small>обработано · окно 5 с</small></span><svg id="spark" viewBox="0 0 260 42" preserveAspectRatio="none"><polyline points="" /></svg></div><div class="metric-grid"><div><span>Инференс · p50</span><strong id="infer">—</strong></div><div><span>Инференс · p95</span><strong id="p95">—</strong></div><div><span>Возраст · p50</span><strong id="age">—</strong></div><div><span>Возраст · p95</span><strong id="age95">—</strong></div></div><div class="timing-list"><div><span>Подготовка / NMS</span><b id="stages">—</b></div><div><span>Ожидание обработки</span><b id="queue">—</b></div><div><span>Отправлено / заменено сервером</span><b id="counts">0 / 0</b></div><div><span>Пропущено до отправки</span><b id="skipped">0</b></div><div><span>Отрисовка / захват, FPS</span><b id="render-fps">—</b></div></div><label class="capture-label" for="capture-fps">Частота виртуальной камеры <select id="capture-fps"><option value="10">10 FPS</option><option value="15">15 FPS</option><option value="30" selected>30 FPS</option><option value="60">60 FPS</option></select></label><p class="note">Свежие кадры заменяют ожидающие. Рамки сохраняются между результатами и могут отставать при движении.</p></section>
  <section class="card detections-card"><div class="card-title"><h2>Распознанные фигуры</h2><span id="detection-count" class="count">0</span></div><div class="table-heading"><span>КЛАСС</span><span>CONFIDENCE</span></div><div id="detections"><p class="empty">Ожидаем первый результат модели</p></div></section>
  <section class="card model-card"><p class="eyebrow">МОДЕЛЬ И СЕССИЯ</p><strong id="model-name">Загрузка модели…</strong><p id="model-info">CPU · batch 1 · прогрев перед замерами</p><div class="export-row"><button id="json" class="quiet">↓ JSON</button><button id="csv" class="quiet">↓ CSV</button></div><small>Метрики последних 5 минут. Точность на этой сцене зависит от обучающих данных.</small></section></aside></div><footer><span>EDGECHESS / VIRTUAL CAMERA</span><span>Python 3.10 · ONNX Runtime · Linux</span></footer></main>`;

const el = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const board = new BoardScene(el("viewport"));
const overlay = el<HTMLCanvasElement>("overlay");
const context = overlay.getContext("2d")!;
const fen = el<HTMLInputElement>("fen");
board.onChange = () => {
  fen.value = board.chess.fen();
  el("turn").textContent = board.chess.isCheckmate()
    ? "Мат"
    : board.chess.isDraw()
      ? "Ничья"
      : `Ход ${board.chess.turn() === "w" ? "белых" : "чёрных"}${board.chess.isCheck() ? " · шах" : ""}`;
};
board.onMessage = (message) => {
  el("move-help").textContent = message;
};
board.onChange();
el("home").onclick = () => board.home();
el("reset").onclick = () => {
  board.chess.reset();
  board.rebuild();
  board.onMessage("Начальная позиция восстановлена");
};
el("apply").onclick = () => {
  try {
    board.chess.load(fen.value.trim());
    board.rebuild();
    board.onMessage("Позиция загружена");
  } catch {
    board.onMessage("Некорректный FEN. Проверьте запись позиции.");
  }
};
fen.onkeydown = (e) => {
  if (e.key === "Enter") el("apply").click();
};
el<HTMLSelectElement>("promotion").onchange = (e) => {
  board.promotion = (e.target as HTMLSelectElement).value as PieceSymbol;
};

type Detection = { class_name: string; confidence: number; xyxy: number[] };
type Result = {
  type: "result";
  id: number;
  width: number;
  height: number;
  detections: Detection[];
  timings: Record<string, number>;
  counters: { received: number; processed: number; replaced: number };
  session_fps: number;
};
type Sample = {
  at: number;
  id: number;
  age_ms: number;
  inference_ms: number;
  preprocess_ms: number;
  postprocess_ms: number;
  queue_ms: number;
  processing_ms: number;
  detections: number;
};
let socket: WebSocket | null = null,
  ready = false,
  awaitingAck = false,
  encoding = false,
  generation = 0,
  sequence = 0;
let lastResult: Result | null = null,
  lastReceived = 0,
  sent = 0,
  skipped = 0,
  capturedCount = 0;
let samples: Sample[] = [],
  metadata: Record<string, unknown> = {},
  pending = new Map<number, number>();
let ackSince = 0,
  nextCapture = 0,
  frames = 0,
  capturedPrevious = 0,
  renderStart = performance.now(),
  renderFps = 0,
  captureRate = 0;
let streamStart = performance.now(),
  statsHistory: number[] = [];
const worker = new Worker(new URL("./encoder.ts", import.meta.url), {
  type: "module",
});
const status = (message: string, active = false) => {
  el("status").textContent = message;
  el("status-dot").classList.toggle("active", active);
};
function connect() {
  const ownGeneration = ++generation;
  ready = false;
  awaitingAck = false;
  pending.clear();
  lastResult = null;
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/stream`,
  );
  socket = ws;
  status("Подключение…");
  ws.onmessage = (event) => {
    if (ownGeneration !== generation) return;
    const data = JSON.parse(event.data);
    if (data.type === "ready") {
      ready = true;
      metadata = data;
      sent = skipped = capturedCount = 0;
      capturedPrevious = 0;
      samples = [];
      statsHistory = [];
      streamStart = performance.now();
      el("model-name").textContent = data.model;
      el("model-info").textContent =
        `CPU · ${data.threads} потока · ${data.input_size} × ${data.input_size} · прогрев ${data.warmup_runs} проходов`;
      status("Камера подключена", true);
    } else if (data.type === "ack") {
      awaitingAck = false;
    } else if (data.type === "frame_error") {
      pending.delete(data.id);
      status("Ошибка обработки кадра");
    } else if (data.type === "result") {
      const captured = pending.get(data.id);
      // Older results never overwrite newer boxes. Scene movement intentionally
      // does NOT invalidate detections: they behave like a delayed camera feed.
      if (captured === undefined || (lastResult && data.id <= lastResult.id))
        return;
      const now = performance.now();
      lastResult = data;
      lastReceived = now;
      samples.push({
        at: now,
        id: data.id,
        age_ms: now - captured,
        ...data.timings,
        detections: data.detections.length,
      });
      samples = samples.filter((s) => now - s.at < 300000).slice(-18000);
      for (const id of pending.keys()) if (id <= data.id) pending.delete(id);
      status("Поток активен", true);
      renderDetections(data.detections);
    }
  };
  ws.onclose = (event) => {
    if (ownGeneration !== generation) return;
    ready = false;
    awaitingAck = false;
    lastResult = null;
    renderDetections([]);
    status(
      event.code === 1013
        ? "Сервер занят другой камерой"
        : "Нет соединения · повтор через 2 с",
    );
    setTimeout(connect, 2000);
  };
  ws.onerror = () => ws.close();
}
worker.onmessage = (event) => {
  encoding = false;
  const data = event.data;
  if (data.generation !== generation) return;
  if (data.error) {
    status("Ошибка кодирования кадра");
    return;
  }
  if (
    !ready ||
    socket?.readyState !== WebSocket.OPEN ||
    awaitingAck ||
    document.hidden
  ) {
    skipped++;
    return;
  }
  socket.send(data.packet);
  awaitingAck = true;
  ackSince = performance.now();
  sent++;
  pending.set(data.id, data.captured);
  // Replaced frames never get a result; keep this bookkeeping bounded too.
  for (const [id, time] of pending)
    if (performance.now() - time > 30000) pending.delete(id);
};
worker.onerror = () => {
  encoding = false;
  ready = false;
  status("Не удалось запустить кодирование кадров");
};

function renderDetections(detections: Detection[]) {
  el("detection-count").textContent = String(detections.length);
  const list = el("detections");
  list.replaceChildren();
  if (!detections.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = lastResult
      ? "Фигуры не обнаружены"
      : "Ожидаем результат модели";
    list.append(p);
  }
  for (const detection of [...detections].sort(
    (a, b) => b.confidence - a.confidence,
  )) {
    const row = document.createElement("div");
    row.className = "detection-row";
    const name = document.createElement("span");
    name.textContent = detection.class_name;
    const value = document.createElement("b");
    value.textContent = `${(detection.confidence * 100).toFixed(1)}%`;
    row.append(name, value);
    list.append(row);
  }
}
function drawOverlay(now: number) {
  const rect = overlay.getBoundingClientRect();
  const ratio = Math.min(devicePixelRatio, 2);
  if (
    overlay.width !== Math.round(rect.width * ratio) ||
    overlay.height !== Math.round(rect.height * ratio)
  ) {
    overlay.width = Math.round(rect.width * ratio);
    overlay.height = Math.round(rect.height * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  if (
    !el<HTMLInputElement>("boxes").checked ||
    !lastResult ||
    now - lastReceived > 2000
  )
    return;
  context.font = "12px ui-monospace, monospace";
  context.lineWidth = 1.5;
  for (const d of lastResult.detections) {
    const [x, y, w, h] = scaleBox(
      d.xyxy,
      lastResult.width,
      lastResult.height,
      rect.width,
      rect.height,
    );
    context.strokeStyle = "#95ffc0";
    context.strokeRect(x, y, w, h);
    const label = `${d.class_name} ${(d.confidence * 100).toFixed(0)}%`;
    const width = context.measureText(label).width + 10;
    const lx = Math.max(0, Math.min(x, rect.width - width)),
      ly = Math.max(0, y - 20);
    context.fillStyle = "#153a2ce8";
    context.fillRect(lx, ly, width, 19);
    context.fillStyle = "#d9ffe8";
    context.fillText(label, lx + 5, ly + 13);
  }
}
function animate(now: number) {
  requestAnimationFrame(animate);
  board.render();
  drawOverlay(now);
  frames++;
  if (now - renderStart >= 1000) {
    renderFps = (frames * 1000) / (now - renderStart);
    captureRate =
      ((capturedCount - capturedPrevious) * 1000) / (now - renderStart);
    capturedPrevious = capturedCount;
    frames = 0;
    renderStart = now;
  }
  if (awaitingAck && now - ackSince > 5000) socket?.close();
  const fps = Number(el<HTMLSelectElement>("capture-fps").value);
  if (now >= nextCapture && ready && !document.hidden) {
    nextCapture = now + 1000 / fps;
    if (encoding || awaitingAck || (socket?.bufferedAmount ?? 0) > 0) {
      skipped++;
      return;
    }
    encoding = true;
    const id = ++sequence,
      currentGeneration = generation,
      captured = performance.now();
    capturedCount++;
    board
      .snapshot()
      .then((bitmap) =>
        worker.postMessage(
          { bitmap, id, captured, generation: currentGeneration },
          [bitmap],
        ),
      )
      .catch(() => {
        encoding = false;
        status("Не удалось снять кадр");
      });
  }
}
const ms = (n: number | null) => (n === null ? "—" : `${n.toFixed(1)} мс`);
setInterval(() => {
  const now = performance.now();
  const recent = samples.filter((s) => now - s.at < 5000);
  const duration = Math.min(5, (now - streamStart) / 1000);
  const fps = recent.length / Math.max(duration, 0.1);
  el("fps").textContent = fps.toFixed(1);
  el("infer").textContent = ms(
    percentile(
      recent.map((s) => s.inference_ms),
      50,
    ),
  );
  el("p95").textContent = ms(
    percentile(
      recent.map((s) => s.inference_ms),
      95,
    ),
  );
  el("age").textContent = ms(
    percentile(
      recent.map((s) => s.age_ms),
      50,
    ),
  );
  el("age95").textContent = ms(
    percentile(
      recent.map((s) => s.age_ms),
      95,
    ),
  );
  el("stages").textContent = `${ms(
    percentile(
      recent.map((s) => s.preprocess_ms),
      50,
    ),
  )} / ${ms(
    percentile(
      recent.map((s) => s.postprocess_ms),
      50,
    ),
  )}`;
  el("queue").textContent = ms(
    percentile(
      recent.map((s) => s.queue_ms),
      50,
    ),
  );
  el("counts").textContent = `${sent} / ${lastResult?.counters.replaced ?? 0}`;
  el("skipped").textContent = String(skipped);
  el("render-fps").textContent =
    `${renderFps.toFixed(0)} / ${captureRate.toFixed(0)}`;
  statsHistory.push(fps);
  statsHistory = statsHistory.slice(-50);
  const max = Math.max(10, ...statsHistory);
  el("spark")
    .querySelector("polyline")!
    .setAttribute(
      "points",
      statsHistory
        .map((v, i) => `${(i * 260) / 49},${40 - (v / max) * 36}`)
        .join(" "),
    );
  el("scene-message").textContent = document.hidden
    ? "Вкладка скрыта · захват приостановлен"
    : ready && (!lastResult || now - lastReceived > 2000)
      ? "Ожидаем свежий результат…"
      : "";
  if (lastResult && now - lastReceived > 2000) {
    lastResult = null;
    renderDetections([]);
    if (ready) status("Нет свежих результатов");
  }
}, 500);

function download(format: "json" | "csv") {
  const now = performance.now();
  const rows = samples
    .filter((s) => now - s.at < 300000)
    .map(({ at, ...s }) => ({ elapsed_ms: at - streamStart, ...s }));
  const report = {
    exported_at: new Date().toISOString(),
    model: metadata,
    settings: {
      capture_fps: Number(el<HTMLSelectElement>("capture-fps").value),
      width: 960,
      height: 720,
      jpeg_quality: 0.88,
    },
    counters: { sent, skipped, ...lastResult?.counters },
    samples: rows,
  };
  const keys = rows.length
    ? Object.keys(rows[0])
    : ["elapsed_ms", "id", "age_ms", "inference_ms"];
  const content =
    format === "json"
      ? JSON.stringify(report, null, 2)
      : [
          keys.join(","),
          ...rows.map((row) =>
            keys.map((k) => row[k as keyof typeof row]).join(","),
          ),
        ].join("\n");
  const url = URL.createObjectURL(
    new Blob([content], {
      type: format === "json" ? "application/json" : "text/csv",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `edgechess-${Date.now()}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
el("json").onclick = () => download("json");
el("csv").onclick = () => download("csv");
if (!("OffscreenCanvas" in window))
  status("Нужен браузер с поддержкой OffscreenCanvas");
else connect();
requestAnimationFrame(animate);
