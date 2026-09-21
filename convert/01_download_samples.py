"""Download individual Kaggle files, not the entire dataset.

Keeps source paths and SHA256 hashes for reproducibility. Calibration uses train;
evaluation uses test. These are smoke-test subsets, not a full quality benchmark.
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import random
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
DATASET = "imtkaggleteam/chess-pieces-detection-image-dataset"
API = "https://www.kaggle.com/api/v1/datasets"


def fetch(url):
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "EdgeChess-conversion/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def list_files(directory):
    cache = directory / "kaggle_files.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    names, token = [], None
    while True:
        params = {"pageSize": 1000}
        if token:
            params["pageToken"] = token
        payload = json.loads(fetch(f"{API}/list/{DATASET}?{urllib.parse.urlencode(params)}"))
        names.extend(x["name"] for x in payload["datasetFiles"])
        token = payload.get("nextPageToken") or payload.get("nextPageTokenNullable")
        print(f"Listed {len(names)} files", flush=True)
        if not token:
            break
    cache.write_text(json.dumps(sorted(set(names)), indent=2), encoding="utf-8")
    return sorted(set(names))


def download(source, destination):
    url = f"{API}/download/{DATASET}/{urllib.parse.quote(source, safe='')}"
    if not destination.exists():
        data = fetch(url)
        # Kaggle sometimes wraps an individual file in ZIP. Never extract paths.
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [x for x in archive.infolist() if not x.is_dir()]
                matches = [x for x in entries if PurePosixPath(x.filename).name == destination.name]
                if len(matches) != 1:
                    raise ValueError(f"Unexpected ZIP contents for {source}")
                data = archive.read(matches[0])
        if data.lstrip().startswith((b"<!", b"<html")):
            raise ValueError(f"Kaggle returned HTML instead of {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return {"source": source, "path": destination.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-count", type=int, default=20)
    parser.add_argument("--calibration-count", type=int, default=100)
    args = parser.parse_args()
    if min(args.test_count, args.calibration_count) < 1:
        parser.error("Counts must be positive")
    directory = ROOT / "data"
    directory.mkdir(exist_ok=True)
    names = list_files(directory)
    jobs, selections = [], {}
    for split, count in [("test", args.test_count), ("train", args.calibration_count)]:
        # Match the regular detection dataset used by the notebook, not its OBB copy.
        candidates = [n for n in names if n.startswith(f"Chess_pieces/{split}/")
                      and n.lower().endswith((".jpg", ".jpeg", ".png"))]
        # Dataset includes copies both in split/ and split/images/.
        # Select each filename once, preferring the conventional images directory.
        unique = {}
        for name in sorted(candidates):
            basename = PurePosixPath(name).name
            if basename not in unique or "/images/" in name:
                unique[basename] = name
        candidates = list(unique.values())
        if len(candidates) < count:
            raise ValueError(f"Only {len(candidates)} images in Chess_pieces/{split}; requested {count}")
        selected = random.Random(42).sample(sorted(candidates), count)
        selections[split] = selected
        for source in selected:
            jobs.append((source, directory / split / "images" / PurePosixPath(source).name))
            stem = PurePosixPath(source).stem
            labels = [n for n in names if n.startswith(f"Chess_pieces/{split}/")
                      and PurePosixPath(n).name == stem + ".txt"]
            if labels:
                preferred = next((n for n in labels if "/labels/" in n), labels[0])
                jobs.append((preferred, directory / split / "labels" / (stem + ".txt")))
    for name in names:
        if name.startswith("Chess_pieces/") and (name.endswith(".yaml") or "README" in name):
            jobs.append((name, directory / "source" / PurePosixPath(name).name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda pair: download(*pair), jobs))
    test_hashes = {r["sha256"] for r in records if r["path"].startswith("data/test/images/")}
    train_hashes = {r["sha256"] for r in records if r["path"].startswith("data/train/images/")}
    if test_hashes & train_hashes:
        raise ValueError("Identical image files occur in calibration and test")
    (directory / "manifest.json").write_text(json.dumps({"dataset": DATASET, "seed": 42,
        "selection": selections, "files": records}, indent=2), encoding="utf-8")
    print(f"Downloaded/verified {len(records)} files. Manifest: {directory / 'manifest.json'}")


if __name__ == "__main__":
    main()
