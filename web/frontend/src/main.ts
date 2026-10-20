import "./style.css";
import { BoardScene } from "./scene";
import { percentile, scaleBox, comparePlacements } from "./metrics.mjs";
import type { PieceSymbol } from "chess.js";
import { AdvisorPanel } from "./advisor";
import { layout } from "./layout";

document.querySelector<HTMLDivElement>("#app")!.innerHTML = layout;

const el = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const board = new BoardScene(el("viewport"));
const advisor = new AdvisorPanel(board.chess, uci => board.showAdvice(uci));
const overlay = el<HTMLCanvasElement>("overlay");
const context = overlay.getContext("2d")!;
const stillFrame=el<HTMLCanvasElement>("still-frame");
const fen = el<HTMLInputElement>("fen");
board.onChange = () => {
  fen.value = board.chess.fen();
  el("turn").textContent = board.chess.isCheckmate()
    ? "Мат"
    : board.chess.isDraw()
      ? "Ничья"
      : `Ход ${board.chess.turn() === "w" ? "белых" : "чёрных"}${board.chess.isCheck() ? " · шах" : ""}`;
  advisor.update();
  clearRecognitionSummary("Позиция изменилась · ожидаем свежий кадр");
};
board.onMessage = (message) => {
  el("move-help").textContent = message;
};
board.onChange();
el("home").onclick = () => board.home();
el("reset").onclick = () => {
  advisor.clearAdvice();
  board.chess.reset();
  board.rebuild();
  board.onMessage("Начальная позиция восстановлена");
};
el("apply").onclick = () => {
  try {
    board.chess.load(fen.value.trim());
    advisor.clearAdvice();
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
  profile: string; backend: string; status: string; placement: string | null; warnings: string[];
  game_revision?: number;
  pieces: (Detection & { square: string; symbol: string })[]; stages: Record<string, Record<string, number>>;
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
  stages: Record<string, Record<string, number>>;
};
let paused = false;
let configurationFailed = false;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let resultPlacement: string | null = null;
const selection = (id: string) => el<HTMLSelectElement>(id).value;
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
function showConfiguration(data: { model: string; provider: string; profile: string; input_size: number; warmup_runs: number; backend: string; models: { conversion_verified: boolean }[] }) {
  el("model-name").textContent=data.model;
  el("model-info").textContent=`${data.provider} · ${data.profile} · ${data.input_size} × ${data.input_size} · прогрев ${data.warmup_runs} проходов${data.models.some(m => !m.conversion_verified) ? " · погрешность конвертации превышает порог" : ""}`;
  el("backend-tag").textContent=data.backend;
}
function connect() {
  if (paused) return;
  const ownGeneration = ++generation;
  ready = false;
  awaitingAck = false;
  pending.clear();
  lastResult = null;
  clearRecognitionSummary("Подключение к потоку…");
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/stream?${processingQuery()}`,
  );
  socket = ws;
  status("Подключение…");
  ws.onmessage = (event) => {
    if (ownGeneration !== generation) return;
    const data = JSON.parse(event.data);
    if (data.type === "ready") {
      ready = true;
      configurationFailed = false;
      metadata = data;
      sent = skipped = capturedCount = 0;
      capturedPrevious = 0;
      samples = [];
      statsHistory = [];
      streamStart = performance.now();
      showConfiguration(data);
      status(data.models.some((m: { conversion_verified: boolean }) => !m.conversion_verified) ? "Камера подключена · проверка погрешности конвертации не пройдена" : "Камера подключена", true);
    } else if (data.type === "configuration_error") {
      configurationFailed = true;
      paused = true; el("pause").textContent = "Возобновить поток";
      status(data.message);
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
        stages: data.stages,
      });
      samples = samples.filter((s) => now - s.at < 300000).slice(-18000);
      for (const id of pending.keys()) if (id <= data.id) pending.delete(id);
      status("Поток активен", true);
      renderDetections(data.detections);
      renderRecognition(data, selection("source-mode") === data.profile, framePositions.get(data.id));
      advisor.observe(data, framePositions.get(data.id));
      for (const id of framePositions.keys()) if (id <= data.id) framePositions.delete(id);
    }
  };
  ws.onclose = (event) => {
    if (ownGeneration !== generation) return;
    ready = false;
    awaitingAck = false;
    lastResult = null;
    advisor.invalidateVision();
    clearRecognitionSummary("Нет соединения с потоком");
    renderDetections([]);
    if (paused) return;
    status(
      event.code === 1013
        ? "Сервер занят другой камерой"
        : "Нет соединения · повтор через 2 с",
    );
    reconnectTimer = setTimeout(connect, 2000);
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
    (!paused && now - lastReceived > 2000)
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
  if (now >= nextCapture && ready && !paused && !document.hidden) {
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
    framePositions.set(id, board.chess.fen().split(" ")[0]);
    if (framePositions.size > 100) framePositions.delete(framePositions.keys().next().value!);
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
  el("counts").textContent = `${sent} / ${lastResult?.counters?.replaced ?? 0}`;
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
    : ready && (!lastResult || (!paused && now - lastReceived > 2000))
      ? "Ожидаем свежий результат…"
      : "";
  if (lastResult && (!paused && now - lastReceived > 2000)) {
    lastResult = null;
    renderDetections([]);
    clearRecognitionSummary("Нет свежего результата");
    if (ready) status("Нет свежих результатов");
  }
}, 500);

function download(format: "json" | "csv") {
  const now = performance.now();
  const rows = samples
    .filter((s) => now - s.at < 300000)
    .map(({ at, stages, ...s }) => ({ elapsed_ms: at - streamStart, ...s,
      ...Object.fromEntries(Object.entries(stages).flatMap(([name, times]) => Object.entries(times).map(([metric, value]) => [`${name}_${metric}`, value]))) }));
  const report = {
    exported_at: new Date().toISOString(),
    model: metadata,
    settings: {
      capture_fps: Number(el<HTMLSelectElement>("capture-fps").value),
      width: 960,
      height: 720,
      jpeg_quality: 0.88,
      source: stillFrame.hidden ? selection("source-mode") : "jpeg",
      orientation: selection("orientation"), theme: selection("theme"), shape: selection("shape"), light: Number(el<HTMLInputElement>("light").value),
    },
    counters: { sent, skipped, ...lastResult?.counters },
    samples: rows,
  };
  const keys = rows.length
    ? [...new Set(rows.flatMap(row => Object.keys(row)))]
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
const framePositions = new Map<number, string>();
function clearRecognitionSummary(message: string) {
  el("recognition-score").textContent = "—";
  el("recognition-badge").textContent = "Ожидание";
  el("recognition-badge").dataset.state = "neutral";
  el("accuracy").textContent = message;
}
function renderRecognition(result: Result, fromScene: boolean, expected?: string) {
  resultPlacement = result.placement;
  el("vision-status").textContent = `${result.profile} / ${result.backend}: ${result.status}${result.warnings?.length ? " · " + result.warnings.join(", ") : ""}`;
  el("recognized-placement").textContent = result.placement ?? "Нет распознанной расстановки";
  const comparison = fromScene ? comparePlacements(result.placement, expected) : null;
  const current = expected === board.chess.fen().split(" ")[0];
  const badge = el("recognition-badge");
  if (comparison && current) {
    const exact = comparison.correct === comparison.total;
    const reliable = result.status === "ok" && !result.warnings?.length;
    el("recognition-score").textContent = `${comparison.correct}/${comparison.total}`;
    badge.textContent = !reliable ? "Проверьте" : exact ? "Совпадает" : "Есть отличия";
    badge.dataset.state = exact && reliable ? "ok" : "warning";
    el("accuracy").textContent = !reliable ? "Есть предупреждения распознавания"
      : exact ? "Расстановка совпала с кадром сцены" : "Расстановка отличается от кадра сцены";
  } else {
    clearRecognitionSummary(!fromScene ? "Кадр не сравнивается с виртуальной доской"
      : !current ? "Ожидаем кадр текущей позиции" : "Расстановка не распознана");
    badge.textContent = !fromScene ? "Без сравнения" : !current ? "Ожидание" : "Нет позиции";
    badge.dataset.state = fromScene && current ? "warning" : "neutral";
  }
  renderFen();
}
function renderFen() {
  const color = selection("active-color"), castling = el<HTMLInputElement>("castling").value, ep = el<HTMLInputElement>("en-passant").value;
  const valid = /^(-|K?Q?k?q?)$/.test(castling) && castling.length > 0 && /^(-|[a-h][36])$/.test(ep);
  el("recognized-fen").textContent = resultPlacement && valid ? `${resultPlacement} ${color} ${castling} ${ep} 0 1` : "";
}
for (const id of ["active-color","castling","en-passant"]) el(id).onchange = renderFen;
function appearance() {
  advisor.invalidateVision();
  board.setAppearance(selection("source-mode") as "2d" | "3d",selection("theme"),selection("shape"),Number(el<HTMLInputElement>("light").value));
}
for (const id of ["source-mode","theme","shape","light"]) el(id).onchange = appearance;
el<HTMLInputElement>("piece-set").onchange = async e => {
  const file=(e.target as HTMLInputElement).files?.[0]; if (!file) return;
  try {
    if (file.size > 20*1024*1024) throw new Error("GLB больше 20 МБ");
    await board.loadPieceSet(await file.arrayBuffer());
    const option=el<HTMLSelectElement>("shape").querySelector<HTMLOptionElement>('option[value="glb"]')!;
    option.disabled=false; el<HTMLSelectElement>("shape").value="glb";
    appearance();
  } catch(error) { board.onMessage(String(error)); }
};
function reconnect() {
  advisor.invalidateVision();
  clearRecognitionSummary(paused ? "Поток приостановлен" : "Настройки изменились · ожидаем кадр");
  if (reconnectTimer) clearTimeout(reconnectTimer);
  ++generation; socket?.close(); ready=false; lastResult=null; resultPlacement=null; renderFen();
  framePositions.clear(); pending.clear();
  stillFrame.hidden=true; board.renderer.domElement.style.visibility="visible";
  if (!paused) connect();
}
function processingQuery() {
  const query = new URLSearchParams({profile:selection("profile"),backend:selection("backend"),orientation:selection("orientation")});
  query.set("game_id", advisor.gameId);
  if (selection("profile") === "3d") query.set("model",selection("model"));
  return query;
}
function updateModelSelector() {
  el("model-label").hidden = selection("profile") !== "3d";
  el<HTMLSelectElement>("model").disabled = selection("profile") !== "3d";
}
for (const id of ["profile","model","backend","orientation"]) el(id).onchange = () => {
  updateModelSelector();
  if (configurationFailed) {
    configurationFailed=false; paused=false; el("pause").textContent="Приостановить поток";
  }
  reconnect();
};
el("pause").onclick = () => {
  paused=!paused; el("pause").textContent=paused?"Возобновить поток":"Приостановить поток"; reconnect();
  if (paused) status("Поток приостановлен");
};
el("analyze").onclick = async () => {
  const file=el<HTMLInputElement>("image-file").files?.[0];
  if (!file) { status("Выберите JPEG"); return; }
  if (!paused) { status("Сначала приостановите поток"); return; }
  try {
    const query=processingQuery();
    const response=await fetch(`/api/analyze?${query}`,{method:"POST",headers:{"Content-Type":"image/jpeg"},body:file});
    const data=await response.json();
    if (!response.ok) throw new Error(data.detail);
    const bitmap=await createImageBitmap(file);
    stillFrame.width=bitmap.width; stillFrame.height=bitmap.height;
    stillFrame.getContext("2d")!.drawImage(bitmap,0,0); bitmap.close();
    stillFrame.hidden=false; board.renderer.domElement.style.visibility="hidden";
    lastResult=data; lastReceived=performance.now();
    metadata=data.configuration; showConfiguration(data.configuration);
    renderRecognition(data,false); renderDetections(data.detections);
    status("Сохранённый кадр обработан");
  } catch(error) { status(String(error)); }
};
el("save-frame").onclick = async () => {
  const bitmap=await board.snapshot();
  const canvas=new OffscreenCanvas(960,720); canvas.getContext("2d")!.drawImage(bitmap,0,0,960,720); bitmap.close();
  const blob=await canvas.convertToBlob({type:"image/jpeg",quality:.88});
  const url=URL.createObjectURL(blob), link=document.createElement("a");
  link.href=url; link.download="edgechess-frame.jpg"; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
appearance();
if (!("OffscreenCanvas" in window))
  status("Нужен браузер с поддержкой OffscreenCanvas");
else void initialize();
async function initialize() {
  try {
    const response=await fetch("/api/health");
    if (!response.ok) throw new Error("Сервер не готов");
    const data=await response.json();
    advisor.setAvailable(Boolean(data.stockfish?.available));
    const models=el<HTMLSelectElement>("model");
    models.replaceChildren(...Object.entries(data.model_choices as Record<string,string>).map(([key,label])=>new Option(label,key)));
    if (data.profile === "3d") models.value=data.models[0].key;
    el<HTMLSelectElement>("profile").value=data.profile;
    el<HTMLSelectElement>("backend").value=data.backend;
    el<HTMLSelectElement>("source-mode").value=data.profile;
    updateModelSelector(); appearance(); connect();
  } catch {
    status("Нет соединения · повтор через 2 с");
    reconnectTimer=setTimeout(initialize,2000);
  }
}
requestAnimationFrame(animate);
