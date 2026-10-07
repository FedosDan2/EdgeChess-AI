"""Measure the complete configured pipeline on preloaded BGR images."""

import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from .inference import ROOT
from vision.pipeline import Pipeline
from vision.config import PROFILES, BACKENDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--profile", choices=PROFILES, default="2d")
    parser.add_argument("--backend", choices=BACKENDS, default="onnx")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    frames = [cv2.imread(str(p)) for p in args.images]
    if any(f is None for f in frames):
        parser.error("Cannot decode an input image")
    pipeline = Pipeline(args.profile, args.backend, directory=ROOT / "convert/artifacts")
    samples = []
    try:
        for i in range(args.runs):
            result = pipeline.predict(frames[i % len(frames)])
            samples.append(
                {
                    "status": result["status"],
                    **result["timings"],
                    "stages": result["stages"],
                }
            )
        times = [s["processing_ms"] for s in samples]
        report = {
            **pipeline.describe(),
            "runs": args.runs,
            "images": [str(p) for p in args.images],
            "scope": "Full pipeline: preprocessing, model(s), NMS, geometry; preloaded BGR, no JPEG/network/render",
            "latency_ms": {
                "mean": float(np.mean(times)),
                "p50": float(np.percentile(times, 50)),
                "p95": float(np.percentile(times, 95)),
            },
            "pipeline_fps": 1000 / float(np.mean(times)),
            "samples": samples,
        }
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
