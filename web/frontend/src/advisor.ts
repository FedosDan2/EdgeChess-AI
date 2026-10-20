import type { Chess } from "chess.js";

/** History is authoritative for game rules; recognition remains independent. */
export class AdvisorPanel {
  readonly gameId = Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join("");
  private revision = 0;
  private fingerprint = "";
  private synced = -1;
  private thinking = false;
  private available = true;
  private visionMatches = 0;
  private visionAt = 0;
  private syncError = "";
  private adviceGeneration = 0;
  private speechActive = false;
  private speechStop: Promise<unknown> = Promise.resolve();
  private speechPolling = false;
  private element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

  constructor(private chess: Chess, private showAdvice: (uci: string | null) => void) {
    this.element("advisor-side").onchange = () => this.update();
    this.element("advisor-vision").onchange = () => {
      this.clearAdvice();
      this.render();
    };
    this.element("ask-advice").onclick = () => void this.ask();
    this.element("advisor-speech").onchange = () => {
      if (!this.element<HTMLInputElement>("advisor-speech").checked) this.stopSpeech();
    };
    this.element("sync-game").onclick = () => { this.fingerprint = ""; this.update(); };
    setInterval(() => this.render(), 500);
    setInterval(() => void this.pollSpeech(), 1000);
  }

  private stopSpeech() {
    this.element("speech-status").textContent = "";
    if (!this.speechActive) return;
    this.speechActive = false;
    this.speechStop = fetch("/api/speech/stop", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: this.gameId, revision: this.revision }),
    }).catch(() => undefined);
  }

  private renderSpeech(state: string) {
    const messages: Record<string, string> = {
      queued: "Озвучка: в очереди", synthesizing: "Озвучка: синтез речи…",
      playing: "Звук на аудиовыходе сервера", done: "Ход озвучен на сервере",
      unavailable: "Нет озвучки: проверьте настройку TTS на сервере",
      error: "Ошибка озвучки: см. журнал сервера",
    };
    this.element("speech-status").textContent = messages[state] || "";
    if (!["queued", "synthesizing", "playing"].includes(state)) this.speechActive = false;
  }

  private async pollSpeech() {
    if (!this.speechActive || this.speechPolling || this.thinking) return;
    this.speechPolling = true;
    const generation = this.adviceGeneration;
    try {
      const response = await fetch("/api/speech");
      if (!response.ok) return;
      const data = await response.json();
      if (generation === this.adviceGeneration && this.speechActive
          && data.game_id === this.gameId && data.revision === this.revision) this.renderSpeech(data.state);
    } catch { /* Audio status must never interrupt chess controls. */ }
    finally { this.speechPolling = false; }
  }

  setAvailable(available: boolean) { this.available = available; this.render(); }

  clearAdvice() {
    this.stopSpeech();
    ++this.adviceGeneration;
    this.element("advice-result").textContent = "";
    this.element("advice-meta").textContent = "";
    this.showAdvice(null);
  }

  update() {
    const history = this.chess.history({ verbose: true });
    const payload = {
      initial_fen: history.length ? history[0].before : this.chess.fen(),
      moves: history.map(m => m.from + m.to + (m.promotion || "")),
      side: this.element<HTMLSelectElement>("advisor-side").value,
    };
    const fingerprint = JSON.stringify(payload);
    if (fingerprint === this.fingerprint && !this.syncError) return;
    this.fingerprint = fingerprint;
    const revision = ++this.revision;
    this.invalidateVision();
    this.clearAdvice();
    this.syncError = "";
    this.render();
    void fetch("/api/game", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, game_id: this.gameId, revision }),
    }).then(async response => {
      const data = await response.json();
      if (revision !== this.revision) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ошибка истории партии");
      this.synced = revision;
      this.element("game-history").textContent = `История: ${data.plies} полуходов · версия ${revision} · FEN: ${data.fen}`;
    }).catch(error => {
      if (revision === this.revision) this.syncError = String(error);
    }).finally(() => this.render());
  }

  invalidateVision() { this.stopSpeech(); this.visionMatches = 0; this.visionAt = 0; }

  observe(result: { game_revision?: number; status: string; warnings: string[]; placement: string | null }, expected?: string) {
    const now = performance.now();
    const matches = result.game_revision === this.revision && result.status === "ok" && !result.warnings?.length
      && result.placement === this.chess.fen().split(" ")[0] && result.placement === expected;
    this.visionMatches = matches ? (now - this.visionAt <= 3000 ? this.visionMatches + 1 : 1) : 0;
    this.visionAt = now;
    this.render();
  }

  private render() {
    const requireVision = this.element<HTMLInputElement>("advisor-vision").checked;
    const side = this.element<HTMLSelectElement>("advisor-side").value;
    let reason = "Готово: подсказка только по запросу";
    let disabled = false;
    if (this.thinking) { reason = "Stockfish рассчитывает ход…"; disabled = true; }
    else if (!this.available) { reason = "Stockfish недоступен на сервере"; disabled = true; }
    else if (this.syncError) { reason = this.syncError; disabled = true; }
    else if (this.synced !== this.revision) { reason = "Синхронизация истории…"; disabled = true; }
    else if (this.chess.isGameOver()) { reason = "Партия завершена"; disabled = true; }
    else if (this.chess.turn() !== side) { reason = "Сейчас ход другой стороны"; disabled = true; }
    else if (requireVision && (this.visionMatches < 2 || performance.now() - this.visionAt > 3000)) {
      reason = "Ожидаем два свежих совпадения YOLO с позицией сцены"; disabled = true;
    }
    else if (!requireVision) reason = "Режим отладки: только история UI, без подтверждения YOLO";
    this.element<HTMLButtonElement>("ask-advice").disabled = disabled;
    this.element("advice-status").textContent = reason;
  }

  private async ask() {
    this.render();
    if (this.element<HTMLButtonElement>("ask-advice").disabled) return;
    const revision = this.revision;
    const requireVision = this.element<HTMLInputElement>("advisor-vision").checked;
    this.thinking = true; this.render();
    this.clearAdvice();
    const generation = this.adviceGeneration;
    try {
      await this.speechStop;
      if (revision !== this.revision || generation !== this.adviceGeneration) return;
      const speak = this.element<HTMLInputElement>("advisor-speech").checked;
      this.speechActive = speak;
      const response = await fetch("/api/advice", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ game_id: this.gameId, revision, require_vision: requireVision, speak }),
      });
      const result = await response.json();
      if (revision !== this.revision || generation !== this.adviceGeneration) return;
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Ошибка расчёта");
      this.element("advice-result").textContent =
        `${result.move_san} · ${result.move_uci}` +
        ` · ${result.source === "history_only" ? "только история UI" : "история подтверждена YOLO"}. Ход не применён.`;
      this.element("advice-meta").textContent = `${result.engine} · расчёт ${Math.round(result.elapsed_ms)} мс`;
      this.showAdvice(result.move_uci);
      if (this.speechActive) this.renderSpeech(result.speech?.state || "disabled");
    } catch (error) {
      this.stopSpeech();
      if (revision === this.revision && generation === this.adviceGeneration) this.element("advice-result").textContent = String(error);
    } finally { this.thinking = false; this.render(); }
  }
}
