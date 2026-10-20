"""Import only the supplied Piper voice from a ZIP; never execute archive code."""
import argparse
import hashlib
from pathlib import Path
import zipfile

FILES = {
    "ru_RU-irina-medium.onnx": "8ff38212d23da300bbe3705c645e6e5b9475f0bfde01558eb17813e22acaaaaa",
    "ru_RU-irina-medium.onnx.json": "c2ec28bb38e2b59e93b959b3e40348c1afebbd272f30fed5d41205d08e98a9d7",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/tts")
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        data = {name: archive.read(f"edge/piper_models/ru/{name}") for name in FILES}
    for name, content in data.items():
        if hashlib.sha256(content).hexdigest() != FILES[name]:
            parser.error(f"Unexpected voice checksum: {name}")
        target = args.output / name
        if target.exists() and target.read_bytes() != content:
            parser.error(f"Refusing to overwrite different file: {target}")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in data.items():
        (args.output / name).write_bytes(content)
    print(f"Imported verified voice into {args.output}")


if __name__ == "__main__":
    main()
