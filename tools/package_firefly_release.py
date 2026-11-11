"""Build a complete offline ARM64 release, including a private portable Python."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.download_stockfish import download
from tools.import_tts import import_voice


def command(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/edgechess-firefly-latest.tar.gz")
    args = parser.parse_args()
    cache = ROOT / ".cache/firefly-release"
    cache.mkdir(parents=True, exist_ok=True)
    download("aarch64", cache / "stockfish")
    import_voice(cache / "tts")
    # Pin the interpreter independently from the build machine's Python.
    command("uv", "python", "install", "cpython-3.10.21-linux-aarch64-gnu",
            "--install-dir", cache / "python", "--no-bin")
    python = cache / "python/cpython-3.10.21-linux-aarch64-gnu"
    requirements = cache / "requirements.txt"
    command("uv", "export", "--project", "web", "--locked", "--no-dev", "--extra", "rknn",
            "--extra", "tts", "--no-hashes", "--no-emit-project", "--no-annotate",
            "--output-file", requirements)
    with tempfile.TemporaryDirectory(prefix="release-", dir=cache) as temporary:
        stage = Path(temporary)
        deps = stage / "site-packages"
        command("uv", "pip", "install", "--target", deps, "--python-version", "3.10",
                "--python-platform", "aarch64-manylinux_2_35", "--no-deps", "-r", requirements)
        base = stage / "base.tar"
        command(sys.executable, "tools/package_firefly.py", "--profiles", "3d", "--3d-models", "chess3d_m",
                "--backends", "rknn_int8", "rknn_fp16", "--with-tts", "--tts-dir", cache / "tts",
                "--stockfish-dir", cache / "stockfish/aarch64", "--output", base)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        manifest = {}
        def remember(info):
            if "__pycache__" in Path(info.name).parts or info.name.endswith(".pyc"):
                return None
            return info
        with tarfile.open(args.output, "w:gz", compresslevel=3) as archive:
            def add(path, name):
                if path.is_file():
                    manifest[name] = digest(path)
                archive.add(path, arcname=name, recursive=False, filter=remember)
            def tree(directory, name):
                add(directory, name)
                for path in sorted(directory.rglob("*")):
                    if "__pycache__" not in path.parts and path.suffix != ".pyc":
                        add(path, str(Path(name) / path.relative_to(directory)))
            with tarfile.open(base) as original:
                for member in original:
                    stream = original.extractfile(member) if member.isfile() else None
                    if member.isfile():
                        data = stream.read()
                        if member.name == "PACKAGE.json":
                            package = json.loads(data)
                            package.update(standalone=True, python="3.10.21", offline=True,
                                           source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
                            data = (json.dumps(package, indent=2) + "\n").encode()
                            member.size = len(data)
                        manifest[member.name] = hashlib.sha256(data).hexdigest()
                        stream = io.BytesIO(data)
                    archive.addfile(member, stream)
            tree(python, ".runtime/python")
            tree(deps, ".runtime/site-packages")
            add(ROOT / "tools/firefly_standalone.sh", "edgechess.sh")
            add(ROOT / "tools/firefly_standalone.py", "tools/firefly_standalone.py")
            add(ROOT / "docs/firefly.md", "START_HERE.md")
            audio = b'''</usr/share/alsa/alsa.conf>
pcm.edgechess {
  type plug
  slave { pcm "hw:CARD=rockchipes8388,DEV=0" rate 48000 channels 2 format S16_LE }
  ttable.0.0 0.2
  ttable.0.1 0.2
}
'''
            manifest["audio.conf"] = hashlib.sha256(audio).hexdigest()
            for name, data in [("audio.conf", audio), ("FILES.sha256", "".join(
                    f"{value}  {name}\n" for name, value in sorted(manifest.items())).encode())]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        args.output.with_suffix(args.output.suffix + ".sha256").write_text(
            f"{digest(args.output)}  {args.output.name}\n")
        print(f"Release: {args.output} ({args.output.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
