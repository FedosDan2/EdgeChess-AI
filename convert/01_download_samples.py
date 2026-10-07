"""Small reproducible subsets: ChessRender360 RGB/JSON or local Roboflow YOLO exports."""

import argparse
import concurrent.futures
import hashlib
import io
import json
import random
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = "mmkoya/chessrender360"
API = "https://www.kaggle.com/api/v1/datasets"
ROBOFLOW = {
    "board2d": ("devil3515", "chessboard-detection-loqg5"),
    "pieces2d": ("chess-raa7q", "chess-cfal9"),
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "EdgeChess/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError(f"Dataset server returned HTTP {exc.code}") from None
        except (OSError, TimeoutError):
            pass
        time.sleep(attempt + 1)
    raise RuntimeError("Dataset download failed after three attempts")


def download(source, destination, version):
    if not destination.exists():
        url = f"{API}/download/{DATASET}/{urllib.parse.quote(source, safe='')}?datasetVersionNumber={version}"
        data = fetch(url)
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [
                    n for n in archive.namelist() if Path(n).name == destination.name
                ]
                if len(entries) != 1:
                    raise ValueError("Unexpected single-file archive")
                data = archive.read(entries[0])
        if data.lstrip().startswith((b"<html", b"<!")):
            raise ValueError("Expected dataset file, got HTML")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return {
        "source": source,
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


def save_manifest(model, records, source, **extra):
    directory = ROOT / "data" / model
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"source": source, "seed": 42, "files": records, **extra}
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"{model}: {len(records)} files; {directory / 'manifest.json'}", flush=True)


def chess360(train_count, test_count, version):
    # Same lexicographic annotation order and split as setup_dataset_3d.py.
    ids = sorted(range(10000), key=lambda i: f"annotation_{i}.json")
    random.Random(42).shuffle(ids)
    groups = {"train": ids[:8000], "test": ids[9000:]}
    selections = {
        s: random.Random(43).sample(v, train_count if s == "train" else test_count)
        for s, v in groups.items()
    }
    jobs = []
    for split, selected in selections.items():
        for index in selected:
            jobs.append(
                (
                    f"ChessRender360/rgb/rgb_{index}.jpeg",
                    ROOT / f"data/chess3d/{split}/images/rgb_{index}.jpeg",
                    split,
                )
            )
            jobs.append(
                (
                    f"ChessRender360/annotations/annotation_{index}.json",
                    ROOT / f"data/chess3d/{split}/annotations/annotation_{index}.json",
                    split,
                )
            )

    def run(job):
        source, dest, split = job
        return {**download(source, dest, version), "split": split}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(run, jobs))
    save_manifest("chess3d", records, DATASET, version=version, selection=selections)


def import_yolo(model, directory, train_count, test_count):
    import yaml

    config = yaml.safe_load((directory / "data.yaml").read_text())
    names = config["names"]
    if isinstance(names, list):
        names = dict(enumerate(names))
    mapping = {
        int(i): (0 if model == "board2d" else list(PIECES).index(name) + 1)
        for i, name in names.items()
        if (name == "chessboard" if model == "board2d" else name in PIECES)
    }
    if not mapping:
        raise ValueError("No expected labels in data.yaml")
    if model == "pieces2d" and len(mapping) != 12:
        raise ValueError("The export must contain all twelve piece classes")
    records = []
    for split, count in [("train", train_count), ("test", test_count)]:
        candidates = sorted((directory / split / "images").glob("*"))
        if not candidates:
            raise ValueError(f"Missing {split} images in {directory}")
        selected = random.Random(42).sample(candidates, min(count, len(candidates)))
        for image in selected:
            if image.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            label = directory / split / "labels" / (image.stem + ".txt")
            if not label.exists():
                raise ValueError(f"Missing annotation {label}")
            dest = ROOT / "data" / model / split / "images" / image.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(image.read_bytes())
            output_label = dest.parent.parent / "labels" / label.name
            output_label.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            for line in label.read_text().splitlines():
                fields = line.split()
                if len(fields) != 5:
                    raise ValueError(f"Invalid detection label {label}")
                cls = int(fields[0])
                if cls in mapping:
                    lines.append(" ".join([str(mapping[cls]), *fields[1:]]))
            output_label.write_text("\n".join(lines) + "\n")
            for path in (dest, output_label):
                records.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "split": split,
                        "source": str(image if path == dest else label),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
    save_manifest(
        model,
        records,
        "/".join(ROBOFLOW[model]),
        export=str(directory),
        class_mapping=mapping,
    )


PIECES = (
    "b-bishop",
    "b-king",
    "b-knight",
    "b-pawn",
    "b-queen",
    "b-rook",
    "w-bishop",
    "w-king",
    "w-knight",
    "w-pawn",
    "w-queen",
    "w-rook",
)


def download_roboflow(model, version):
    key = os.environ.get("ROBOFLOW_API_KEY")
    env_file = ROOT.parent / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ROBOFLOW_API_KEY":
                key = value.strip().strip("\"'")
    if not key:
        raise ValueError(
            "Set ROBOFLOW_API_KEY in the environment or the ignored root .env; alternatively supply --export"
        )
    workspace, project = ROBOFLOW[model]
    endpoint = f"https://api.roboflow.com/{workspace}/{project}"
    query = urllib.parse.urlencode({"api_key": key})
    if version is None:
        metadata = json.loads(fetch(endpoint + "?" + query))
        versions = metadata.get(
            "versions", metadata.get("project", {}).get("versions", [])
        )
        versions = [
            int(v.get("version", str(v.get("id", "")).split("/")[-1])) for v in versions
        ]
        if not versions:
            raise ValueError("No published dataset versions; specify --version")
        version = max(versions)
    response = json.loads(fetch(f"{endpoint}/{version}/yolov8?{query}"))
    link = response.get("export", {}).get("link")
    if not link:
        raise ValueError("Roboflow did not return a YOLOv8 export")
    data = fetch(link)
    directory = ROOT / "data" / model / "export" / str(version)
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            destination = (directory / entry.filename).resolve()
            if not destination.is_relative_to(directory.resolve()):
                raise ValueError("Unsafe archive path")
            if entry.is_dir():
                continue
            if destination.suffix.lower() not in (
                ".jpg",
                ".jpeg",
                ".png",
                ".txt",
                ".yaml",
            ):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(entry))
    return directory, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", choices=("board2d", "pieces2d", "chess3d"), required=True
    )
    parser.add_argument(
        "--export",
        type=Path,
        help="Unpacked Roboflow YOLOv8 export containing data.yaml",
    )
    parser.add_argument(
        "--version",
        type=int,
        help="ChessRender360: default 5; Roboflow: latest published YOLOv8 version",
    )
    parser.add_argument("--calibration-count", type=int, default=128)
    parser.add_argument("--test-count", type=int, default=32)
    args = parser.parse_args()
    if min(args.calibration_count, args.test_count) < 1:
        parser.error("Counts must be positive")
    if args.model == "chess3d":
        chess360(args.calibration_count, args.test_count, args.version or 5)
    elif args.export:
        import_yolo(
            args.model, args.export.resolve(), args.calibration_count, args.test_count
        )
    else:
        directory, version = download_roboflow(args.model, args.version)
        import_yolo(args.model, directory, args.calibration_count, args.test_count)
        path = ROOT / "data" / args.model / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["version"] = version
        path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
