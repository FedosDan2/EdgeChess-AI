"""Download the pinned Russian Piper voice and verify its SHA256 checksums."""
import argparse
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
BASE_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/ru/ru_RU/irina/medium"

FILES = {
    "ru_RU-irina-medium.onnx": "8ff38212d23da300bbe3705c645e6e5b9475f0bfde01558eb17813e22acaaaaa",
    "ru_RU-irina-medium.onnx.json": "c2ec28bb38e2b59e93b959b3e40348c1afebbd272f30fed5d41205d08e98a9d7",
}


def verified(path, digest):
    if not path.exists():
        return False
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Refusing to overwrite different file: {path}")
    return True


def import_voice(output):
    output = Path(output)
    missing = [name for name, digest in FILES.items() if not verified(output / name, digest)]
    output.mkdir(parents=True, exist_ok=True)
    # Stage and verify every missing file before publishing any of them. A failed
    # or interrupted download leaves existing files intact and no partial model.
    with tempfile.TemporaryDirectory(prefix=".tts-", dir=output) as temporary:
        for name in missing:
            print(f"Downloading {name}…", flush=True)
            digest = hashlib.sha256()
            size = 0
            with urlopen(f"{BASE_URL}/{name}", timeout=120) as response, (Path(temporary) / name).open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 128 * 1024 * 1024:
                        raise ValueError(f"Unexpected download size: {name}")
                    digest.update(chunk)
                    target.write(chunk)
            if digest.hexdigest() != FILES[name]:
                raise ValueError(f"Unexpected voice checksum: {name}")
        # Recheck in case another invocation installed files during the download.
        missing = [name for name in missing if not verified(output / name, FILES[name])]
        for name in missing:
            (Path(temporary) / name).replace(output / name)
    print(f"Verified Piper voice ready in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/tts")
    args = parser.parse_args()
    try:
        import_voice(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
