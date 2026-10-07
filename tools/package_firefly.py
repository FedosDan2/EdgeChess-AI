"""Build a minimal runtime archive locally; never connects to the board."""

import argparse
import io
import json
import sys
import subprocess
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.config import ROOT, PROFILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=["3d"])
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=("onnx", "rknn_fp16", "rknn_int8"),
        default=["rknn_fp16"],
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/firefly-runtime.tar"
    )
    args = parser.parse_args()
    files = [
        *(p for p in ROOT.glob("vision/*.py") if p.name != "evaluate.py"),
        *ROOT.glob("web/backend/*.py"),
        ROOT / "convert/common.py",
        ROOT / "web/pyproject.toml",
        ROOT / "web/uv.lock",
    ]
    dist = ROOT / "web/frontend/dist"
    if not (dist / "index.html").exists():
        parser.error("Build web/frontend first")
    files.extend(p for p in dist.rglob("*") if p.is_file())
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
            "--no-hashes",
            "--no-emit-project",
            "--no-annotate",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.encode()
    reports = []
    for key in dict.fromkeys(k for p in args.profiles for k in PROFILES[p]):
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
        for path, report in reports:
            data = json.dumps(report, indent=2).encode()
            info = tarfile.TarInfo(path.relative_to(ROOT).as_posix())
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    print(
        f"{args.output}: {args.output.stat().st_size / 1024**2:.2f} MiB; profiles={args.profiles}; backends={args.backends}"
    )


if __name__ == "__main__":
    main()
