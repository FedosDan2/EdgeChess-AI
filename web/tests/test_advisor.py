import os
import struct
import threading
from time import monotonic

import chess
from fastapi.testclient import TestClient
import pytest

from backend.advisor import AdviceRequest, GameStore, GameUpdate, StockfishAdvisor
from backend.app import create_app


def update(**kwargs):
    return GameUpdate(game_id="demo", revision=1, initial_fen=chess.STARTING_FEN, **kwargs)


def test_history_legality_rights_and_custom_fen():
    store = GameStore()
    result = store.sync(update(moves=["e2e4", "a7a6", "e4e5", "d7d5"]))
    game = store.get("demo")
    assert game.board.ep_square == chess.D6
    assert game.board.has_kingside_castling_rights(chess.WHITE)
    assert result["plies"] == 4
    assert len(game.board.move_stack) == 4
    assert store.sync(game.update) == result  # idempotent retry
    ep_history = game.update.moves + ["e5d6"]
    with pytest.raises(ValueError):
        store.sync(update(moves=["e2e5"]))
    with pytest.raises(ValueError):
        GameStore().sync(update(moves=["e2e5"]))
    with pytest.raises(ValueError):
        GameStore().sync(GameUpdate(game_id="x", revision=1, initial_fen="8/8/8/8/8/8/8/8 w - - 0 1"))
    store.sync(GameUpdate(game_id="demo", revision=2, initial_fen=chess.STARTING_FEN, moves=ep_history))
    assert store.get("demo").board.piece_at(chess.D5) is None
    assert store.get("demo").board.piece_at(chess.D6).symbol() == "P"
    castling = GameStore()
    castling.sync(update(moves=["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"]))
    castled = castling.get("demo").board
    assert castled.king(chess.WHITE) == chess.G1
    assert castled.piece_at(chess.F1).symbol() == "R"
    assert not castled.has_castling_rights(chess.WHITE)
    assert castled.fullmove_number == 4 and castled.halfmove_clock == 5
    custom = GameUpdate(game_id="custom", revision=1,
        initial_fen="7k/P7/8/8/8/8/8/7K w - - 0 1", moves=["a7a8q"])
    store.sync(custom)
    assert store.get("custom").board.piece_at(chess.A8).symbol() == "Q"


def test_draw_history_and_wrong_side():
    store = GameStore()
    store.sync(update(moves=["g1f3", "g8f6", "f3g1", "f6g8"] * 2))
    assert store.get("demo").board.can_claim_threefold_repetition()
    with pytest.raises(ValueError, match="завершена"):
        store.snapshot(AdviceRequest(game_id="demo", revision=1, require_vision=False))
    store = GameStore()
    store.sync(update(side="b"))
    with pytest.raises(ValueError, match="другой стороны"):
        store.snapshot(AdviceRequest(game_id="demo", revision=1, require_vision=False))


def test_independent_vision_gate_and_revision():
    store = GameStore()
    store.sync(update())
    request = AdviceRequest(game_id="demo", revision=1)
    result = {"status": "ok", "warnings": [], "placement": chess.Board().board_fen()}
    with pytest.raises(ValueError):
        store.snapshot(request)
    for _ in range(2):
        store.observe("demo", 1, result, monotonic())
    assert store.snapshot(request).fen() == chess.STARTING_FEN
    store.observe("demo", 1, {**result, "warnings": ["cell_conflict:e4"]}, monotonic())
    with pytest.raises(ValueError):
        store.snapshot(request)
    for _ in range(2):
        store.observe("demo", 1, result, monotonic() - 5)
    with pytest.raises(ValueError):
        store.snapshot(request)
    store.sync(GameUpdate(game_id="demo", revision=2, initial_fen=chess.STARTING_FEN, moves=["e2e4"]))
    store.observe("demo", 1, result, monotonic())
    assert store.get("demo").matches == 0
    with pytest.raises(ValueError):
        store.get("demo", 1)
    store.clear_vision("missing")


class Detector:
    def describe(self):
        return {"model": "fake"}


class Advisor:
    closed = False

    def describe(self):
        return {"available": True}

    def best_move(self, board, game_id):
        move = next(iter(board.legal_moves))
        return {"move_uci": move.uci(), "move_san": board.san(move), "fen_in": board.fen()}

    def close(self):
        self.closed = True


def test_api_no_automatic_moves_and_vision_not_client_supplied():
    advisor = Advisor()
    with TestClient(create_app(Detector, lambda: advisor)) as client:
        assert client.post("/api/game", json=update().model_dump()).status_code == 200
        assert client.post("/api/game", json={**update().model_dump(), "moves": ["e2e5"]}).status_code == 422
        request = {"game_id": "demo", "revision": 1}
        assert client.post("/api/advice", json=request).status_code == 409
        response = client.post("/api/advice", json={**request, "require_vision": False})
        assert response.status_code == 200
        assert response.json()["source"] == "history_only"
        assert client.app.state.games.get("demo").board.fen() == chess.STARTING_FEN
        assert client.post("/api/game", json={**update().model_dump(), "moves": ["x" * 100]}).status_code == 422
    assert advisor.closed


def test_stream_vision_gate_live_and_cleared_on_disconnect():
    class RecognizingDetector(Detector):
        def predict(self, jpeg):
            return {"status": "ok", "warnings": [], "placement": chess.Board().board_fen(),
                    "timings": {}, "detections": [], "width": 640, "height": 640}

    with TestClient(create_app(RecognizingDetector, Advisor)) as client:
        client.post("/api/game", json=update().model_dump())
        request = {"game_id": "demo", "revision": 1}
        with client.websocket_connect("/api/stream?game_id=demo") as ws:
            assert ws.receive_json()["type"] == "ready"
            for frame_id in (1, 2):
                ws.send_bytes(struct.pack(">Q", frame_id) + b"jpeg")
                while True:
                    message = ws.receive_json()
                    if message["type"] == "result":
                        assert message["game_revision"] == 1
                        break
                if frame_id == 1:
                    assert client.post("/api/advice", json=request).status_code == 409
            result = client.post("/api/advice", json=request)
            assert result.status_code == 200
            assert result.json()["source"] == "history_verified_by_yolo"
        # Synchronize cleanup with another event-loop request.
        import time
        for _ in range(100):
            if not client.app.state.busy:
                break
            time.sleep(.01)
        assert client.post("/api/advice", json=request).status_code == 409


def test_stale_result_busy_and_separate_worker():
    entered, release = threading.Event(), threading.Event()

    class SlowAdvisor(Advisor):
        def best_move(self, board, game_id):
            entered.set()
            assert release.wait(5)
            return super().best_move(board, game_id)

    with TestClient(create_app(Detector, SlowAdvisor)) as client:
        client.post("/api/game", json=update().model_dump())
        request = {"game_id": "demo", "revision": 1, "require_vision": False}
        responses = []
        thread = threading.Thread(target=lambda: responses.append(client.post("/api/advice", json=request)))
        thread.start()
        try:
            assert entered.wait(5)
            assert client.post("/api/advice", json=request).status_code == 409
            assert client.get("/api/health").status_code == 200
            newer = {**update().model_dump(), "revision": 2, "moves": ["e2e4"]}
            assert client.post("/api/game", json=newer).status_code == 200
        finally:
            release.set()
            thread.join(5)
        assert responses[0].status_code == 409
        assert not client.app.state.advice_busy


def test_engine_error_releases_admission():
    class Broken(Advisor):
        def best_move(self, *args):
            raise RuntimeError("failed")

    with TestClient(create_app(Detector, Broken)) as client:
        client.post("/api/game", json=update().model_dump())
        request = {"game_id": "demo", "revision": 1, "require_vision": False}
        for _ in range(2):
            assert client.post("/api/advice", json=request).status_code == 503
            assert not client.app.state.advice_busy


def test_store_bounded():
    store = GameStore(capacity=1)
    store.sync(update())
    store.sync(GameUpdate(game_id="next", revision=1, initial_fen=chess.STARTING_FEN))
    with pytest.raises(ValueError):
        store.get("demo")


@pytest.mark.skipif(not os.getenv("STOCKFISH_PATH"), reason="Set STOCKFISH_PATH for real CPU engine")
def test_real_stockfish(monkeypatch):
    monkeypatch.setenv("EDGECHESS_STOCKFISH_SECONDS", "0.1")
    advisor = StockfishAdvisor()
    try:
        board = chess.Board()
        result = advisor.best_move(board, "test")
        assert chess.Move.from_uci(result["move_uci"]) in board.legal_moves
        assert board.fen() == chess.STARTING_FEN
        assert "Stockfish" in result["engine"]
        assert advisor.engine is not None
        engine = advisor.engine
        advisor.best_move(board, "test")
        assert advisor.engine is engine
    finally:
        advisor.close()
