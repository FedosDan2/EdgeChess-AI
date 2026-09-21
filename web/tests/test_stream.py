"""Protocol tests: bounded queue, real overlap, lifecycle and malformed input."""
import asyncio
import struct
import time

from fastapi.testclient import TestClient

from backend.app import LatestFrame, create_app


class SlowDetector:
    def describe(self):
        return {"model": "test", "threads": 1}

    def predict(self, jpeg):
        time.sleep(.08)
        return {"detections": [], "width": 960, "height": 720,
                "timings": {"inference_ms": 80}}


def test_latest_frame_replaces_pending():
    async def check():
        slot = LatestFrame()
        for i in range(100):
            slot.put(i)
        assert slot.queue.qsize() == 1
        assert slot.dropped == 99
        assert await slot.queue.get() == 99
    asyncio.run(check())


def test_stream_overlaps_and_keeps_latest():
    with TestClient(create_app(SlowDetector)) as client:
        with client.websocket_connect("/api/stream") as ws:
            assert ws.receive_json()["type"] == "ready"
            results = []
            for i in range(1, 16):
                ws.send_bytes(struct.pack(">Q", i) + b"jpeg")
                while True:
                    message = ws.receive_json()
                    if message["type"] == "ack":
                        assert message["id"] == i
                        break
                    results.append(message)
            while not results or results[-1]["id"] != 15:
                results.append(ws.receive_json())
            assert results[-1]["counters"]["replaced"] > 0
            assert results[-1]["counters"]["processed"] < 15
            assert results[-1]["timings"]["queue_ms"] >= 0
            with client.websocket_connect("/api/stream") as second:
                assert second.receive()["code"] == 1013
        # Disconnect drains native work and releases the worker for another user.
        for _ in range(100):
            if not client.app.state.busy:
                break
            time.sleep(.01)
        with client.websocket_connect("/api/stream") as again:
            assert again.receive_json()["type"] == "ready"


def test_invalid_packet_closes_connection():
    with TestClient(create_app(SlowDetector)) as client:
        with client.websocket_connect("/api/stream") as ws:
            ws.receive_json()
            ws.send_text("not a binary frame")
            assert ws.receive()["code"] == 1008


def test_duplicate_id_is_rejected():
    with TestClient(create_app(SlowDetector)) as client:
        with client.websocket_connect("/api/stream") as ws:
            ws.receive_json()
            packet = struct.pack(">Q", 1) + b"jpeg"
            ws.send_bytes(packet)
            assert ws.receive_json()["type"] == "ack"
            ws.send_bytes(packet)
            while True:
                message = ws.receive()
                if message["type"] == "websocket.close":
                    assert message["code"] == 1008
                    break
