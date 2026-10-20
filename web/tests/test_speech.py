import asyncio
import importlib.util
import io
import os
import sys
import threading
import time
import wave

import chess
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.speech import DEFAULT_MODEL, move_text, SpeechService
from backend.advisor import StockfishAdvisor
from test_advisor import Advisor, Detector, update


def test_move_text_and_unchanged_board():
    board = chess.Board()
    assert move_text(board, "g1f3") == "Конь с жэ один на эф три"
    assert board.fen() == chess.STARTING_FEN
    with pytest.raises(ValueError):
        move_text(board, "e2e5")
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert move_text(board, "e1g1") == "Короткая рокировка"
    assert move_text(board, "e1c1") == "Длинная рокировка"
    board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
    assert "превращением в коня" in move_text(board, "a7a8n")
    assert move_text(board, "a7a8q").endswith("Шах!")
    board = chess.Board()
    for move in ["e4", "a6", "e5", "d5"]:
        board.push_san(move)
    assert "берёт на дэ шесть, взятие на проходе" in move_text(board, "e5d6")
    board = chess.Board()
    for move in ["f3", "e5", "g4"]:
        board.push_san(move)
    assert move_text(board, "d8h4").endswith("Мат!")


def test_api_optional_unavailable_tts(monkeypatch):
    monkeypatch.setenv("EDGECHESS_TTS_MODEL", "/nonexistent/voice.onnx")
    with TestClient(create_app(Detector, Advisor)) as client:
        client.post("/api/game", json=update().model_dump())
        request = {"game_id": "demo", "revision": 1, "require_vision": False}
        assert client.post("/api/advice", json=request).json()["speech"]["state"] == "disabled"
        result = client.post("/api/advice", json={**request, "speak": True})
        assert result.status_code == 200
        assert result.json()["speech"]["state"] == "unavailable"
        assert client.get("/api/speech").json()["state"] == "unavailable"
        assert client.post("/api/speech/stop", json=request).status_code == 200
        assert client.get("/api/speech").json()["state"] == "idle"


async def until(predicate):
    for _ in range(400):
        if predicate():
            return
        await asyncio.sleep(.01)
    raise AssertionError("Speech worker did not settle")


def test_bounded_latest_job_and_cancel_during_synthesis(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Synth:
        def generate(self, text):
            calls.append(text)
            entered.set()
            assert release.wait(5)
            return b"wav"

    player = tmp_path / "aplay"
    log = tmp_path / "played"
    player.write_text(f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\nsys.stdin.buffer.read()\nPath({str(log)!r}).write_text('played')\n")
    player.chmod(0o755)

    async def run():
        service = SpeechService(Synth(), str(player))
        try:
            board = chess.Board()
            service.submit(board, "e2e4", "demo", 1, lambda: True)
            await until(entered.is_set)
            for move in ["d2d4", "b1c3", "g1f3"]:
                service.submit(board, move, "demo", 1, lambda: True)
            release.set()
            await until(lambda: service.state == "done")
            assert calls == [move_text(board, "e2e4"), move_text(board, "g1f3")]
            assert log.read_text() == "played"
            log.unlink()
            service.submit(board, "d2d4", "demo", 1, lambda: False)
            await until(lambda: service.state == "idle")
            assert not log.exists()
        finally:
            release.set()
            await service.close()
    asyncio.run(run())


def test_playback_failure_and_stop(tmp_path):
    class Synth:
        def generate(self, text):
            return b"wav"

    async def run():
        service = SpeechService(Synth(), "/nonexistent/player")
        try:
            service.submit(chess.Board(), "e2e4", "demo", 1, lambda: True)
            await until(lambda: service.state == "error")
            player = tmp_path / "aplay"
            player.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
            player.chmod(0o755)
            service.player = str(player)
            service.submit(chess.Board(), "e2e4", "demo", 2, lambda: True)
            await until(lambda: service.state == "playing")
            service.cancel("other", 2)
            assert service.state == "playing"
            service.cancel("demo", 1)
            assert service.state == "playing"
            service.cancel("demo", 2)
            await until(lambda: service.process is None)
            assert service.state == "idle"
        finally:
            await service.close()
    asyncio.run(run())


def test_stop_while_stockfish_thinks_prevents_speech():
    entered, release = threading.Event(), threading.Event()
    calls = []

    class SlowAdvisor(Advisor):
        def best_move(self, board, game_id):
            entered.set()
            assert release.wait(5)
            return super().best_move(board, game_id)

    class Synth:
        def generate(self, text):
            calls.append(text)
            return b"wav"

    with TestClient(create_app(Detector, SlowAdvisor,
                    lambda: SpeechService(Synth(), "/nonexistent/player"))) as client:
        client.post("/api/game", json=update().model_dump())
        request = {"game_id": "demo", "revision": 1, "require_vision": False, "speak": True}
        responses = []
        thread = threading.Thread(target=lambda: responses.append(client.post("/api/advice", json=request)))
        thread.start()
        try:
            assert entered.wait(5)
            assert client.post("/api/speech/stop", json=request).status_code == 200
        finally:
            release.set()
            thread.join(5)
        assert responses[0].status_code == 200
        assert responses[0].json()["speech"]["state"] == "disabled"
        assert not calls


def test_position_change_while_synthesizing_discards_audio():
    entered, release = threading.Event(), threading.Event()

    class Synth:
        def generate(self, text):
            entered.set()
            assert release.wait(5)
            return b"wav"

    with TestClient(create_app(Detector, Advisor,
                    lambda: SpeechService(Synth(), "/nonexistent/player"))) as client:
        client.post("/api/game", json=update().model_dump())
        response = client.post("/api/advice", json={"game_id": "demo", "revision": 1,
                                                   "require_vision": False, "speak": True})
        assert response.status_code == 200
        try:
            assert entered.wait(5)
            # Health and game sync remain responsive during native synthesis.
            assert client.get("/api/health").status_code == 200
            newer = {**update().model_dump(), "revision": 2, "moves": ["e2e4"]}
            assert client.post("/api/game", json=newer).status_code == 200
        finally:
            release.set()
        assert client.get("/api/speech").json()["state"] == "idle"


@pytest.mark.skipif(not (os.getenv("STOCKFISH_PATH") and DEFAULT_MODEL.is_file()
                        and importlib.util.find_spec("piper")),
                    reason="Import the voice, install extra tts and set STOCKFISH_PATH")
def test_real_stockfish_piper_and_wav_output(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGECHESS_TTS_MODEL", str(DEFAULT_MODEL))
    monkeypatch.setenv("EDGECHESS_STOCKFISH_SECONDS", "0.1")
    output = tmp_path / "move.wav"
    player = tmp_path / "aplay"
    player.write_text(f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\nPath({str(output)!r}).write_bytes(sys.stdin.buffer.read())\n")
    player.chmod(0o755)
    advisor = StockfishAdvisor()
    calls = []
    original = advisor.best_move

    def best_move(*args):
        calls.append(1)
        return original(*args)

    advisor.best_move = best_move
    with TestClient(create_app(Detector, lambda: advisor,
                    lambda: SpeechService(player=str(player)))) as client:
        client.post("/api/game", json=update().model_dump())
        response = client.post("/api/advice", json={"game_id": "demo", "revision": 1,
                                                   "require_vision": False, "speak": True})
        assert response.status_code == 200
        result = response.json()
        assert result["speech"]["state"] == "queued"
        assert result["speech"]["text"] == move_text(chess.Board(), result["move_uci"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = client.get("/api/speech").json()["state"]
            if state in ("done", "error"):
                break
            time.sleep(.05)
        assert state == "done"
        assert calls == [1]  # No second search for TTS.
        synth = client.app.state.speech.synthesizer
        assert synth.voice.session.get_providers() == ["CPUExecutionProvider"]
        assert synth.voice.session.get_session_options().intra_op_num_threads == 1
        text = result["speech"]["text"]
        assert synth.generate(text) is synth.cache[text]
        assert client.app.state.games.get("demo").board.fen() == chess.STARTING_FEN
        with wave.open(io.BytesIO(output.read_bytes())) as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 22050
            assert audio.getnframes() > 1000
