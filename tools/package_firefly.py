"""Build a minimal runtime archive locally; never connects to the board."""

import argparse
import io
import json
import hashlib
import sys
import subprocess
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.config import ROOT, PROFILES, MODELS_3D, DEFAULT_3D_MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=["3d"])
    parser.add_argument("--3d-models", nargs="+", choices=MODELS_3D, default=[DEFAULT_3D_MODEL], dest="models_3d")
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=("onnx", "rknn_fp16", "rknn_int8"),
        default=["rknn_fp16"],
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/firefly-runtime.tar"
    )
    parser.add_argument("--stockfish-dir", type=Path, default=ROOT / "artifacts/stockfish/aarch64")
    parser.add_argument("--with-tts", action="store_true", help="Include locally imported Piper voice and TTS dependencies")
    parser.add_argument("--reuse-artifacts", action="store_true",
                        help="Explicit overlay: reuse previously verified YOLO artifacts on the board")
    args = parser.parse_args()
    files = [
        *(p for p in ROOT.glob("vision/*.py") if p.name != "evaluate.py"),
        *ROOT.glob("web/backend/*.py"),
        ROOT / "convert/common.py",
        ROOT / "web/pyproject.toml",
        ROOT / "web/uv.lock",
        ROOT / "tools/install_firefly.sh",
        ROOT / "tools/run_firefly.sh",
        ROOT / "tools/import_tts.py",
        ROOT / "README.md",
        ROOT / "web/frontend/public/pieces/cburnett/LICENSE.md",
        *ROOT.glob("docs/*.md"),
    ]
    dist = ROOT / "web/frontend/dist"
    if not (dist / "index.html").exists():
        parser.error("Build web/frontend first")
    files.extend(p for p in dist.rglob("*") if p.is_file())
    if args.with_tts:
        from tools.import_tts import FILES
        for name, digest in FILES.items():
            path = ROOT / "artifacts/tts" / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                parser.error(f"Import the supplied TTS voice first: {path}")
            files.append(path)
    requirements = subprocess.run(
        [
            "uv",
            "export",
            "--project",
            str(ROOT / "web"),
            "--locked",
            "--no-dev",
            "--extra",
            "rknn",
            *(["--extra", "tts"] if args.with_tts else []),
            "--no-hashes",
            "--no-emit-project",
            "--no-annotate",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.encode()
    reports = []
    stockfish_manifest = json.loads((args.stockfish_dir / "manifest.json").read_text())
    if stockfish_manifest["architecture"] != "aarch64":
        parser.error("Firefly requires the aarch64 Stockfish distribution")
    for filename, key in [("stockfish", "binary_sha256"), ("upstream.tar.gz", "archive_sha256")]:
        digest = hashlib.sha256((args.stockfish_dir / filename).read_bytes()).hexdigest()
        if digest != stockfish_manifest[key]:
            parser.error(f"Stockfish checksum mismatch: {filename}")
    keys = [key for profile in args.profiles for key in
            (args.models_3d if profile == "3d" else PROFILES[profile])]
    for key in dict.fromkeys(keys):
        if args.reuse_artifacts:
            continue
        directory = ROOT / "convert/artifacts" / key
        files.append(directory / "model.json")
        for backend in args.backends:
            if backend == "onnx":
                files.append(directory / "model.onnx")
            else:
                files.append(directory / backend / "model.rknn")
                report_path = directory / backend / "comparison.json"
                report = json.loads(report_path.read_text())
                reports.append(
                    (
                        report_path,
                        {
                            k: v
                            for k, v in report.items()
                            if k not in ("images", "environment")
                        },
                    )
                )
    for p in files:
        if not p.is_file():
            parser.error(f"Missing runtime artifact: {p}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w") as archive:
        info = tarfile.TarInfo("web/requirements-firefly.txt")
        info.size = len(requirements)
        archive.addfile(info, io.BytesIO(requirements))
        for file in files:
            archive.add(file, arcname=file.relative_to(ROOT))
        for filename in ("stockfish", "manifest.json", "upstream.tar.gz"):
            archive.add(args.stockfish_dir / filename, arcname=f"stockfish/{filename}")
        for path, report in reports:
            data = json.dumps(report, indent=2).encode()
            info = tarfile.TarInfo(path.relative_to(ROOT).as_posix())
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        package = json.dumps({"stockfish": stockfish_manifest, "tts": args.with_tts,
                              "external_yolo_artifacts_required": args.reuse_artifacts,
                              "profiles": args.profiles, "default_3d_model": args.models_3d[0],
                              "models": list(dict.fromkeys(keys)), "backends": args.backends}, indent=2).encode()
        info = tarfile.TarInfo("PACKAGE.json")
        info.size = len(package)
        archive.addfile(info, io.BytesIO(package))
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(f"{checksum}  {args.output.name}\n")
    print(
        f"{args.output}: {args.output.stat().st_size / 1024**2:.2f} MiB; profiles={args.profiles}; backends={args.backends}"
    )


if __name__ == "__main__":
    main()
