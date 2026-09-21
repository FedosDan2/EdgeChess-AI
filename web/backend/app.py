"""One inference worker, one replaceable pending frame, bounded transport.

Binary frame = uint64 big-endian sequence id + JPEG. An ACK means received,
not inferred. The browser waits for ACK before sending again, overlapping
transmission with inference without allowing a TCP backlog to grow.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
import logging
from pathlib import Path
import struct
from time import perf_counter

import anyio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .inference import Detector

MAX_FRAME_BYTES = 2 * 1024 * 1024


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


def create_app(detector_factory=Detector):
    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        app.state.executor = executor
        app.state.busy = False
        try:
            app.state.detector = await asyncio.get_running_loop().run_in_executor(executor, detector_factory)
            yield
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="EdgeChess virtual camera", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ready", **app.state.detector.describe()}

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

        async def send(message):
            async with send_lock:
                await ws.send_json(message)

        async def consume():
            nonlocal processed
            while True:
                frame_id, jpeg, arrival = await slot.queue.get()
                def infer():
                    wait_ms = (perf_counter() - arrival) * 1000
                    result = app.state.detector.predict(jpeg)
                    result["timings"]["queue_ms"] = wait_ms
                    return result
                try:
                    result = await asyncio.get_running_loop().run_in_executor(app.state.executor, infer)
                except Exception:
                    logging.exception("Frame inference failed")
                    await send({"type": "frame_error", "id": frame_id, "message": "Cannot process frame"})
                    continue
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
                slot.put((frame_id, data[8:], perf_counter()))
                await send({"type": "ack", "id": frame_id})

        receiver = None
        try:
            await ws.accept()
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
                    app.state.busy = False

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
