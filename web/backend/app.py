"""One inference worker, one replaceable pending frame, bounded transport.

Binary frame = uint64 big-endian sequence id + JPEG. An ACK means received,
not inferred. The browser waits for ACK before sending again, overlapping
transmission with inference without allowing a TCP backlog to grow.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
import logging
from time import monotonic
from pathlib import Path
import struct
from time import perf_counter

import anyio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles

from .inference import Detector
from .advisor import AdviceRequest, GameStore, GameUpdate, StockfishAdvisor
from .speech import SpeechService

MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024


class LatestFrame:
    """Access only on the event loop: a pending frame is replaced, never piled up."""
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=1)
        self.dropped = 0

    def put(self, frame):
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(frame)


def create_app(detector_factory=Detector, advisor_factory=StockfishAdvisor, speech_factory=SpeechService):
    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        app.state.executor = executor
        app.state.busy = False
        app.state.games = GameStore()
        app.state.advisor = advisor_factory()
        app.state.advice_busy = False
        advice_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stockfish")
        app.state.advice_executor = advice_executor
        app.state.speech = speech_factory()
        try:
            app.state.detector = await asyncio.get_running_loop().run_in_executor(executor, detector_factory)
            yield
        finally:
            await app.state.speech.close()
            await asyncio.get_running_loop().run_in_executor(advice_executor, app.state.advisor.close)
            advice_executor.shutdown(wait=True, cancel_futures=True)
            if hasattr(app.state, "detector") and hasattr(app.state.detector, "close"):
                await asyncio.get_running_loop().run_in_executor(executor, app.state.detector.close)
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="EdgeChess virtual camera", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ready", **app.state.detector.describe(),
                "stockfish": app.state.advisor.describe(), "speech": app.state.speech.describe()}

    @app.get("/api/speech")
    async def speech_status():
        return app.state.speech.describe()

    @app.post("/api/speech/stop")
    async def speech_stop(request: AdviceRequest):
        app.state.speech.cancel(request.game_id, request.revision)
        return app.state.speech.describe()

    @app.post("/api/game")
    async def sync_game(update: GameUpdate):
        try:
            previous = app.state.games.games.get(update.game_id)
            result = app.state.games.sync(update)
            if previous is None or previous.update != update:
                app.state.speech.cancel(update.game_id)
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/advice")
    async def advice(request: AdviceRequest):
        if app.state.advice_busy:
            raise HTTPException(409, "Stockfish уже рассчитывает ход")
        try:
            board = app.state.games.snapshot(request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        app.state.advice_busy = True
        app.state.speech.cancel()
        app.state.speech.owner = (request.game_id, request.revision)
        speech_generation = app.state.speech.generation
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                app.state.advice_executor, app.state.advisor.best_move, board, request.game_id)
            # Discard stale search results; never apply a suggested move.
            try:
                app.state.games.snapshot(request)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            speech = {"state": "disabled"}
            if request.speak and speech_generation == app.state.speech.generation:
                def valid():
                    try:
                        return app.state.games.snapshot(request).fen() == board.fen()
                    except ValueError:
                        return False
                try:
                    speech = app.state.speech.submit(board, result["move_uci"], request.game_id,
                                                     request.revision, valid)
                except Exception:
                    logging.exception("Cannot schedule speech")
                    speech = {"state": "error"}
            return {**result, "speech": speech, "game_id": request.game_id, "revision": request.revision,
                    "source": "history_verified_by_yolo" if request.require_vision else "history_only"}
        except HTTPException:
            raise
        except Exception as exc:
            logging.exception("Stockfish failed")
            raise HTTPException(503, "Stockfish недоступен; проверьте бинарник и журнал сервера") from exc
        finally:
            with anyio.CancelScope(shield=True):
                await asyncio.get_running_loop().run_in_executor(app.state.advice_executor, lambda: None)
                app.state.advice_busy = False

    @app.websocket("/api/stream")
    async def stream(ws: WebSocket):
        # A single stream keeps CPU benchmark results attributable to one camera.
        # No await between checking and claiming the worker.
        if app.state.busy:
            await ws.accept()
            await ws.close(code=1013, reason="Inference worker is occupied")
            return
        app.state.busy = True
        slot = LatestFrame()
        send_lock = asyncio.Lock()
        received = processed = 0
        started = perf_counter()
        worker = None
        orientation = ws.query_params.get("orientation", "white")
        game_id = ws.query_params.get("game_id")
        app.state.games.clear_vision(game_id)
        app.state.speech.cancel(game_id)

        async def send(message):
            async with send_lock:
                await ws.send_json(message)

        async def consume():
            nonlocal processed
            while True:
                frame_id, jpeg, arrival, game_revision, captured_at = await slot.queue.get()
                def infer():
                    wait_ms = (perf_counter() - arrival) * 1000
                    result = (app.state.detector.predict(jpeg, orientation) if hasattr(app.state.detector, "configure")
                              else app.state.detector.predict(jpeg))
                    result["timings"]["queue_ms"] = wait_ms
                    return result
                try:
                    result = await asyncio.get_running_loop().run_in_executor(app.state.executor, infer)
                except Exception:
                    app.state.games.clear_vision(game_id)
                    app.state.speech.revalidate()
                    logging.exception("Frame inference failed")
                    await send({"type": "frame_error", "id": frame_id, "message": "Cannot process frame"})
                    continue
                app.state.games.observe(game_id, game_revision, result, captured_at)
                app.state.speech.revalidate()
                result.update(game_id=game_id, game_revision=game_revision)
                processed += 1
                await send({"type": "result", "id": frame_id, **result,
                            "counters": {"received": received, "processed": processed,
                                         "replaced": slot.dropped},
                            "session_fps": processed / max(perf_counter()-started, .001)})

        async def receive():
            nonlocal received
            last_id = -1
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data is None or not 10 <= len(data) <= MAX_FRAME_BYTES:
                    await ws.close(code=1008, reason="Expected binary id + JPEG, at most 2 MiB")
                    return
                frame_id = struct.unpack(">Q", data[:8])[0]
                if frame_id <= last_id or frame_id > 2**53-1:
                    await ws.close(code=1008, reason="Frame ids must increase and fit JS integers")
                    return
                last_id = frame_id
                received += 1
                game = app.state.games.games.get(game_id)
                slot.put((frame_id, data[8:], perf_counter(),
                          game.update.revision if game else None, monotonic()))
                await send({"type": "ack", "id": frame_id})

        receiver = None
        try:
            await ws.accept()
            if hasattr(app.state.detector, "configure"):
                try:
                    if orientation not in ("white", "black"):
                        raise ValueError("Invalid orientation")
                    await asyncio.get_running_loop().run_in_executor(app.state.executor,
                        app.state.detector.configure, ws.query_params.get("profile", "2d"),
                        ws.query_params.get("backend", "onnx"), ws.query_params.get("model"))
                except (ValueError, OSError, ImportError, RuntimeError) as exc:
                    await send({"type": "configuration_error", "message": str(exc)})
                    await ws.close(code=1008)
                    return
            await send({"type": "ready", **app.state.detector.describe()})
            worker = asyncio.create_task(consume())
            receiver = asyncio.create_task(receive())
            done, _ = await asyncio.wait([worker, receiver], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except WebSocketDisconnect:
            pass
        finally:
            # ASGI may cancel the connection scope on disconnect. Shield cleanup
            # so that the worker is drained and admission is always released.
            with anyio.CancelScope(shield=True):
                try:
                    for task in (worker, receiver):
                        if task is not None:
                            task.cancel()
                            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                                await task
                    # Native ORT keeps running after its asyncio future is cancelled.
                    await asyncio.get_running_loop().run_in_executor(app.state.executor, lambda: None)
                finally:
                    app.state.games.clear_vision(game_id)
                    app.state.speech.cancel(game_id)
                    app.state.busy = False

    @app.post("/api/analyze")
    async def analyze(request: Request):
        if app.state.busy:
            raise HTTPException(409, "Close the live stream before analyzing a saved frame")
        app.state.busy=True
        try:
            if int(request.headers.get("content-length", "0")) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "JPEG exceeds 16 MiB")
            jpeg=await request.body()
            if len(jpeg)>MAX_IMAGE_BYTES:
                raise HTTPException(413, "JPEG exceeds 16 MiB")
            def run():
                detector=app.state.detector
                detector.configure(request.query_params.get("profile","2d"),request.query_params.get("backend","onnx"),request.query_params.get("model"))
                result=detector.predict(jpeg,request.query_params.get("orientation","white"))
                return {**result,"configuration":detector.describe()}
            return await asyncio.get_running_loop().run_in_executor(app.state.executor,run)
        except (ValueError, OSError, ImportError, RuntimeError) as exc:
            raise HTTPException(422,str(exc)) from exc
        finally:
            # Drain native inference even if HTTP disconnect cancels the request.
            with anyio.CancelScope(shield=True):
                await asyncio.get_running_loop().run_in_executor(app.state.executor,lambda:None)
                app.state.busy=False

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
