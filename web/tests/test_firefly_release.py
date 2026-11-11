"""Safety checks for the offline release launcher (no NPU required)."""
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def release(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "tools/firefly_standalone.py"
    spec = importlib.util.spec_from_file_location("firefly_release_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PID", tmp_path / "server.pid")
    monkeypatch.setattr(module, "LOG", tmp_path / "web-ui.log")
    monkeypatch.setattr(module.os, "environ", os.environ.copy())
    return module


def test_no_pid_means_stopped(release):
    assert release.process() is None


def test_stale_pid_means_stopped(release):
    release.PID.write_text("1073741824\n")
    assert release.process() is None


def test_never_stop_another_application(release, monkeypatch):
    release.PID.write_text(str(os.getpid()))
    killed = []
    monkeypatch.setattr(release.os, "kill", lambda *args: killed.append(args))
    with pytest.raises(RuntimeError, match="another process"):
        release.stop()
    assert killed == []


def test_stop_already_stopped_removes_only_stale_pid(release):
    release.PID.write_text("1073741824\n")
    preserved = release.ROOT / "user-file"
    preserved.write_text("keep")
    release.stop()
    assert not release.PID.exists()
    assert preserved.read_text() == "keep"


def test_configure_preserves_explicit_settings(release, monkeypatch):
    monkeypatch.chdir(release.ROOT)
    monkeypatch.setenv("EDGECHESS_BACKEND", "rknn_fp16")
    monkeypatch.setenv("EDGECHESS_AUDIO_DEVICE", "default")
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    release.configure()
    assert os.environ["EDGECHESS_BACKEND"] == "rknn_fp16"
    assert os.environ["EDGECHESS_AUDIO_DEVICE"] == "default"
    assert os.environ["STOCKFISH_PATH"] == str(release.ROOT / "stockfish/stockfish")


def test_background_start_refuses_occupied_port(release, monkeypatch):
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        monkeypatch.setenv("EDGECHESS_BIND_HOST", "127.0.0.1")
        monkeypatch.setenv("EDGECHESS_PORT", str(sock.getsockname()[1]))
        with pytest.raises(OSError):
            release.start()
    assert not release.PID.exists()
