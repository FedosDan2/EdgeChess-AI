"""Offline Piper speech for chess recommendations.

Only one synthesis and one replaceable pending recommendation. All admission and
validity checks run on the API event loop; native ONNX runs on a separate worker.
"""
import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import wave

import chess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "artifacts/tts/ru_RU-irina-medium.onnx"
FILES = dict(zip("abcdefgh", ("а", "бэ", "цэ", "дэ", "е", "эф", "жэ", "аш")))
RANKS = ("один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь")
PIECES = {chess.PAWN: "пешка", chess.KNIGHT: "конь", chess.BISHOP: "слон",
          chess.ROOK: "ладья", chess.QUEEN: "ферзь", chess.KING: "король"}


def square_text(square):
    name = chess.square_name(square)
    return f"{FILES[name[0]]} {RANKS[int(name[1]) - 1]}"


def move_text(board, uci):
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError("Нельзя озвучить нелегальный ход")
    if board.is_castling(move):
        text = "Короткая рокировка" if board.is_kingside_castling(move) else "Длинная рокировка"
    else:
        piece = PIECES[board.piece_type_at(move.from_square)].capitalize()
        action = "берёт на" if board.is_capture(move) else "на"
        text = f"{piece} с {square_text(move.from_square)} {action} {square_text(move.to_square)}"
        if board.is_en_passant(move):
            text += ", взятие на проходе"
        if move.promotion:
            promotion = {chess.QUEEN: "ферзя", chess.ROOK: "ладью",
                         chess.BISHOP: "слона", chess.KNIGHT: "коня"}[move.promotion]
            text += f", с превращением в {promotion}"
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        text += ". Мат!"
    elif after.is_check():
        text += ". Шах!"
    return text


class PiperSynthesizer:
    """Lazy CPU-only voice with bounded in-memory WAV cache, no disk growth."""
    def __init__(self, model, threads=1):
        self.model, self.threads = model, threads
        self.voice = None
        self.cache = OrderedDict()

    def generate(self, text):
        if text in self.cache:
            self.cache.move_to_end(text)
            return self.cache[text]
        if self.voice is None:
            import onnxruntime as ort
            from piper import PiperVoice
            from piper.config import PiperConfig
            options = ort.SessionOptions()
            options.intra_op_num_threads = self.threads
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.voice = PiperVoice(
                session=ort.InferenceSession(str(self.model), sess_options=options,
                                            providers=["CPUExecutionProvider"]),
                config=PiperConfig.from_dict(json.loads(Path(str(self.model) + ".json").read_text())),
            )
        pcm = b"".join(chunk.audio_int16_bytes for chunk in self.voice.synthesize(text))
        if not pcm:
            raise RuntimeError("Piper вернул пустое аудио")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(self.voice.config.sample_rate)
            output.writeframes(pcm)
        data = buffer.getvalue()
        self.cache[text] = data
        while len(self.cache) > 64:
            self.cache.popitem(last=False)
        return data


class SpeechService:
    def __init__(self, synthesizer=None, player=None):
        self.model = Path(os.getenv("EDGECHESS_TTS_MODEL", str(DEFAULT_MODEL)))
        self.player = player or shutil.which("aplay")
        self.device = os.getenv("EDGECHESS_AUDIO_DEVICE", "default")
        threads = int(os.getenv("EDGECHESS_TTS_THREADS", "1"))
        if not 1 <= threads <= 4:
            raise ValueError("EDGECHESS_TTS_THREADS must be 1..4")
        self.synthesizer = synthesizer or PiperSynthesizer(self.model, threads)
        self.available = bool(synthesizer or (self.model.is_file()
            and Path(str(self.model) + ".json").is_file() and importlib.util.find_spec("piper"))) and bool(self.player)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="piper")
        self.generation = 0
        self.pending = None
        self.owner = None
        self.process = None
        self.task = None
        self.state = "idle"
        self.text = ""
        self.closed = False
        self.valid = None
        self.wakeup = asyncio.Event()

    def describe(self):
        return {"available": self.available, "state": self.state, "text": self.text,
                "output": "server", "device": self.device,
                "game_id": self.owner[0] if self.owner else None,
                "revision": self.owner[1] if self.owner else None}

    def cancel(self, game_id=None, revision=None):
        if game_id is not None and self.owner is not None:
            if self.owner[0] != game_id or (revision is not None and self.owner[1] > revision):
                return
        self.generation += 1
        self.pending = None
        self.state = "idle"
        self.text = ""
        if self.process is not None and self.process.returncode is None:
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass

    def submit(self, board, uci, game_id, revision, valid):
        self.cancel()
        self.owner = (game_id, revision)
        if not self.available:
            self.state = "unavailable"
            return self.describe()
        self.text = move_text(board, uci)
        self.valid = valid
        self.state = "queued"
        self.pending = (self.generation, self.text, valid)
        self.wakeup.set()
        if self.task is None:
            self.task = asyncio.create_task(self._run())
        return self.describe()

    def revalidate(self):
        if self.state in ("queued", "synthesizing", "playing") and self.valid and not self.valid():
            self.cancel()

    async def _run(self):
        while not self.closed:
            await self.wakeup.wait()
            self.wakeup.clear()
            job, self.pending = self.pending, None
            if job is None:
                continue
            generation, text, valid = job
            try:
                if generation != self.generation or not valid():
                    if generation == self.generation:
                        self.cancel()
                    continue
                self.state = "synthesizing"
                data = await asyncio.get_running_loop().run_in_executor(
                    self.executor, self.synthesizer.generate, text)
                if generation != self.generation or not valid():
                    if generation == self.generation:
                        self.cancel()
                    continue
                self.process = await asyncio.create_subprocess_exec(
                    self.player, "-q", "-D", self.device, "-t", "wav",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE)
                # Cancellation can arrive while the process is being created.
                if generation != self.generation or not valid():
                    self.process.terminate()
                else:
                    self.state = "playing"
                _, errors = await asyncio.wait_for(self.process.communicate(data), timeout=30)
                if generation == self.generation:
                    self.state = "done" if self.process.returncode == 0 else "error"
                    if self.process.returncode:
                        logging.error("aplay exited %s: %s", self.process.returncode,
                                      errors.decode(errors="replace")[:2000])
            except Exception:
                logging.exception("Speech synthesis/playback failed")
                if self.process is not None and self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
                if generation == self.generation:
                    self.state = "error"
            finally:
                self.process = None

    async def close(self):
        self.cancel()
        self.closed = True
        self.wakeup.set()
        if self.task is not None:
            await self.task
        self.executor.shutdown(wait=True, cancel_futures=True)
