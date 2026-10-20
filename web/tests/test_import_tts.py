import hashlib
import io

import pytest

from tools import import_tts


@pytest.fixture
def voice(monkeypatch):
    files = {"voice.onnx": b"model", "voice.onnx.json": b"config"}
    monkeypatch.setattr(import_tts, "FILES", {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    })
    calls = []

    def download(url, timeout):
        assert url.startswith(import_tts.BASE_URL + "/")
        assert timeout == 120
        name = url.rsplit("/", 1)[1]
        calls.append(name)
        return io.BytesIO(files[name])

    monkeypatch.setattr(import_tts, "urlopen", download)
    return files, calls


def test_download_and_offline_reuse(tmp_path, voice):
    files, calls = voice
    output = tmp_path / "tts"
    import_tts.import_voice(output)
    assert calls == list(files)
    for name, data in files.items():
        assert (output / name).read_bytes() == data
    calls.clear()
    import_tts.import_voice(output)
    assert calls == []
    assert sorted(path.name for path in output.iterdir()) == sorted(files)


def test_existing_different_file_is_preserved(tmp_path, voice):
    files, calls = voice
    name = next(iter(files))
    target = tmp_path / name
    target.write_bytes(b"user data")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        import_tts.import_voice(tmp_path)
    assert target.read_bytes() == b"user data"
    assert calls == []


def test_checksum_failure_does_not_publish_partial_voice(tmp_path, voice):
    files, _ = voice
    files["voice.onnx.json"] = b"corrupted config"
    with pytest.raises(ValueError, match="checksum"):
        import_tts.import_voice(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_interruption_removes_partial_download(tmp_path, voice, monkeypatch):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(import_tts, "urlopen", interrupted)
    with pytest.raises(KeyboardInterrupt):
        import_tts.import_voice(tmp_path)
    assert list(tmp_path.iterdir()) == []
