"""Folder-local, offline Firefly release: check, run, start, stop, status."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PID = ROOT / "server.pid"
LOG = ROOT / "web-ui.log"


def configure():
    os.chdir(ROOT)
    os.environ.setdefault("STOCKFISH_PATH", str(ROOT / "stockfish/stockfish"))
    os.environ.setdefault("EDGECHESS_PROFILE", "3d")
    os.environ.setdefault("EDGECHESS_3D_MODEL", "chess3d_m")
    os.environ.setdefault("EDGECHESS_BACKEND", "rknn_int8")
    os.environ.setdefault("EDGECHESS_STOCKFISH_THREADS", "1")
    os.environ.setdefault("EDGECHESS_STOCKFISH_HASH_MB", "64")
    os.environ.setdefault("EDGECHESS_TTS_THREADS", "1")
    # Never write ~/.asoundrc or change the system mixer.
    if "EDGECHESS_AUDIO_DEVICE" not in os.environ:
        cards = Path("/proc/asound/cards")
        analog = cards.exists() and "rockchipes8388" in cards.read_text()
        os.environ["EDGECHESS_AUDIO_DEVICE"] = "edgechess" if analog else "default"
    if os.environ["EDGECHESS_AUDIO_DEVICE"] == "edgechess":
        os.environ["ALSA_CONFIG_PATH"] = str(ROOT / "audio.conf")


def address():
    return os.getenv("EDGECHESS_BIND_HOST", "127.0.0.1"), int(os.getenv("EDGECHESS_PORT", "8000"))


def health():
    host, port = address()
    if host == "0.0.0.0":
        host = "127.0.0.1"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://{host}:{port}/api/health", timeout=3) as response:
        return json.load(response)


def process():
    if not PID.exists():
        return None
    pid = int(PID.read_text().strip())
    proc = Path("/proc") / str(pid)
    try:
        cwd = Path(os.readlink(proc / "cwd"))
        args = (proc / "cmdline").read_bytes().replace(b"\0", b" ")
    except FileNotFoundError:
        return None
    if cwd != ROOT or b"firefly_standalone.py run" not in args:
        raise RuntimeError(f"PID {pid} belongs to another process; refusing to touch it")
    return pid


def check(audio=False):
    if platform.machine() != "aarch64":
        raise RuntimeError("This release requires Linux ARM64 (aarch64)")
    libc = os.confstr("CS_GNU_LIBC_VERSION")
    if tuple(map(int, libc.split()[-1].split("."))) < (2, 35):
        raise RuntimeError("Stockfish requires glibc >= 2.35; use Ubuntu 22.04/24.04 or newer")
    for line in (ROOT / "FILES.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = ROOT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Integrity check failed: {name}")
    print("OK: release files, ARM64,", libc, flush=True)
    from web.backend.inference import Detector
    detector = Detector()
    try:
        description = detector.describe()
        if description["provider"] != "RKNN NPU":
            raise RuntimeError("Select an RKNN backend for the NPU check")
        print("OK: NPU warmup", description["backend"], flush=True)
    finally:
        detector.close()
    import chess
    import chess.engine
    with chess.engine.SimpleEngine.popen_uci(os.environ["STOCKFISH_PATH"], timeout=20) as engine:
        engine.configure({"Threads": 1, "Hash": 64})
        board = chess.Board()
        move = engine.play(board, chess.engine.Limit(time=.2)).move
        if move not in board.legal_moves:
            raise RuntimeError("Stockfish returned an invalid move")
        print("OK:", engine.id["name"], move.uci(), flush=True)
    from web.backend.speech import PiperSynthesizer, DEFAULT_MODEL
    data = PiperSynthesizer(DEFAULT_MODEL).generate("Конь с жэ один на эф три")
    print("OK: Piper WAV", len(data), "bytes", flush=True)
    player = shutil.which("aplay")
    if not player:
        raise RuntimeError("aplay missing: install alsa-utils (OS prerequisite)")
    if audio:
        subprocess.run([player, "-q", "-D", os.environ["EDGECHESS_AUDIO_DEVICE"], "-t", "wav"],
                       input=data, check=True, timeout=30)
        print("OK: ALSA playback; confirm audibility on the connected speakers", flush=True)
    else:
        print("Audio not played; use: bash edgechess.sh check --audio", flush=True)


def run():
    host, port = address()
    import uvicorn
    uvicorn.run("web.backend.app:app", host=host, port=port, loop="asyncio", ws="websockets",
                ws_max_size=2097152, ws_max_queue=1)


def start():
    pid = process()
    if pid:
        print("Already running, PID", pid)
        return
    host, port = address()
    with socket.socket() as sock:
        sock.bind((host, port))  # Do not mistake another server for this release.
    with LOG.open("ab") as log:
        child = subprocess.Popen([sys.executable, "-s", "-B", str(Path(__file__).resolve()), "run"],
                                 cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
    PID.write_text(str(child.pid) + "\n")
    for _ in range(90):
        if child.poll() is not None:
            PID.unlink(missing_ok=True)
            raise RuntimeError(f"Startup failed; see {LOG}")
        try:
            result = health()
            if result["status"] == "ready":
                print(f"Started PID {child.pid}: http://{host}:{port}")
                print(json.dumps(result, ensure_ascii=False))
                return
        except (OSError, ValueError):
            time.sleep(1)
    raise RuntimeError(f"Startup timeout; see {LOG}. Stop with: bash edgechess.sh stop")


def stop():
    pid = process()
    if pid is None:
        PID.unlink(missing_ok=True)
        print("Already stopped")
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(150):
        if not (Path("/proc") / str(pid)).exists():
            PID.unlink(missing_ok=True)
            print("Stopped", pid)
            return
        time.sleep(.2)
    raise RuntimeError("Shutdown timeout; the process was NOT forcibly killed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "run", "start", "stop", "status"], default="run", nargs="?")
    parser.add_argument("--audio", action="store_true", help="Play a short spoken test during check")
    args = parser.parse_args()
    configure()
    if args.command == "check":
        check(args.audio)
    elif args.command == "status":
        pid = process()
        if pid is None:
            raise RuntimeError("Server is stopped")
        print("PID", pid, json.dumps(health(), ensure_ascii=False))
    else:
        {"run": run, "start": start, "stop": stop}[args.command]()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)
