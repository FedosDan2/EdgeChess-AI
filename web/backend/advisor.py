"""Validated game history and a persistent, bounded CPU Stockfish service.

Renderer state never enters vision. YOLO observations are an independent gate,
not a source of castling/en-passant rights or a replacement for move history.
"""

from collections import OrderedDict
from dataclasses import dataclass
import os
import shutil
from time import monotonic, perf_counter
from typing import Annotated, Literal

import chess
import chess.engine
from pydantic import BaseModel, Field


def finished(board):
    # Match chess.js: repetition/50-move draw at the current position, not a
    # claim that could become available after a prospective next move.
    return board.is_game_over() or board.is_repetition(3) or board.is_fifty_moves()


class GameUpdate(BaseModel):
    game_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    revision: int = Field(ge=0, le=2**53 - 1)
    initial_fen: str = Field(max_length=128)
    moves: list[Annotated[str, Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")]] = Field(default_factory=list, max_length=2048)
    side: Literal["w", "b"] = "w"


class AdviceRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=0)
    require_vision: bool = True


@dataclass
class Game:
    update: GameUpdate
    board: chess.Board
    matches: int = 0
    observed_at: float = 0


class GameStore:
    """Access on the API event loop only; bounded, non-persistent sessions."""

    def __init__(self, capacity=32):
        self.games = OrderedDict()
        self.capacity = capacity

    def sync(self, update):
        previous = self.games.get(update.game_id)
        if previous and update.revision <= previous.update.revision:
            if update == previous.update:
                return self.describe(previous)
            raise ValueError("Устаревшая или противоречивая версия партии")
        board = chess.Board(update.initial_fen)
        if not board.is_valid():
            raise ValueError("Недопустимая начальная позиция")
        for uci in update.moves:
            if finished(board):
                raise ValueError("История содержит ход после завершения партии")
            board.push_uci(uci)  # validates legality, including promotions
        game = Game(update, board)
        self.games[update.game_id] = game
        self.games.move_to_end(update.game_id)
        while len(self.games) > self.capacity:
            self.games.popitem(last=False)
        return self.describe(game)

    def get(self, game_id, revision=None):
        game = self.games.get(game_id)
        if game is None or (revision is not None and game.update.revision != revision):
            raise ValueError("Позиция изменилась или сессия истекла; синхронизируйте партию")
        return game

    @staticmethod
    def describe(game):
        return {
            "game_id": game.update.game_id,
            "revision": game.update.revision,
            "fen": game.board.fen(),
            "placement": game.board.board_fen(),
            "turn": "w" if game.board.turn else "b",
            "side": game.update.side,
            "plies": len(game.board.move_stack),
            "game_over": finished(game.board),
        }

    def clear_vision(self, game_id):
        if game_id in self.games:
            self.games[game_id].matches = 0

    def observe(self, game_id, revision, result, captured_at):
        game = self.games.get(game_id)
        if game is None or game.update.revision != revision:
            return
        matches = (result.get("status") == "ok" and not result.get("warnings")
                   and result.get("placement") == game.board.board_fen())
        fresh = monotonic() - captured_at <= 3
        consecutive = captured_at - game.observed_at <= 3
        game.matches = (game.matches + 1 if consecutive else 1) if matches and fresh else 0
        game.observed_at = captured_at

    def snapshot(self, request):
        game = self.get(request.game_id, request.revision)
        if finished(game.board):
            raise ValueError("Партия завершена")
        if game.board.turn != (game.update.side == "w"):
            raise ValueError("Сейчас ход другой стороны")
        if request.require_vision and (game.matches < 2 or monotonic() - game.observed_at > 3):
            raise ValueError("Нужны два свежих кадра YOLO без предупреждений, совпадающих с историей")
        return game.board.copy(stack=True)


class StockfishAdvisor:
    """Owned by a dedicated single-thread executor, never the inference worker."""

    def __init__(self):
        self.path = os.getenv("STOCKFISH_PATH") or shutil.which("stockfish")
        self.seconds = float(os.getenv("EDGECHESS_STOCKFISH_SECONDS", "1"))
        self.threads = int(os.getenv("EDGECHESS_STOCKFISH_THREADS", "1"))
        self.hash_mb = int(os.getenv("EDGECHESS_STOCKFISH_HASH_MB", "64"))
        if not (0.05 <= self.seconds <= 10 and 1 <= self.threads <= 4 and 1 <= self.hash_mb <= 256):
            raise ValueError("Stockfish limits: seconds 0.05..10, threads 1..4, hash 1..256 MiB")
        self.engine = None

    def describe(self):
        return {"available": bool(self.path and os.path.isfile(self.path)
                                  and os.access(self.path, os.X_OK)),
                "seconds": self.seconds, "threads": self.threads, "hash_mb": self.hash_mb}

    def best_move(self, board, game_id):
        started = perf_counter()
        try:
            if self.engine is None:
                if not self.describe()["available"]:
                    raise RuntimeError("Stockfish недоступен; задайте STOCKFISH_PATH")
                self.engine = chess.engine.SimpleEngine.popen_uci(self.path, timeout=15)
                self.engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
            result = self.engine.play(board, chess.engine.Limit(time=self.seconds),
                                      info=chess.engine.INFO_SCORE, game=game_id)
            if result.move is None or result.move not in board.legal_moves:
                raise RuntimeError("Stockfish не вернул легальный ход")
            move = result.move
            score = result.info.get("score")
            after = board.copy(stack=True)
            after.push(move)
            return {"move_uci": move.uci(), "move_san": board.san(move),
                    "fen_in": board.fen(), "fen_after": after.fen(),
                    "score_cp": score.pov(board.turn).score() if score else None,
                    "mate_in": score.pov(board.turn).mate() if score else None,
                    "engine": self.engine.id.get("name", "Stockfish"),
                    "elapsed_ms": (perf_counter() - started) * 1000,
                    "limits": self.describe()}
        except Exception:
            self.close()
            raise

    def close(self):
        engine, self.engine = self.engine, None
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                engine.close()
