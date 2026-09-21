"""Measure model-only CPU latency on preloaded images; excludes network and NMS."""
import argparse
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .inference import Detector, preprocess_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    detector = Detector()
    tensors = []
    for path in args.images:
        frame = cv2.imread(str(path))
        if frame is None:
            parser.error(f"Cannot read {path}")
        tensors.append(preprocess_image(frame, detector.size)[2])
    timings = []
    for i in range(args.runs):
        start = perf_counter()
        detector.run_tensor(tensors[i % len(tensors)])
        timings.append((perf_counter()-start)*1000)
    report = {**detector.describe(), "runs": args.runs, "images": [str(p) for p in args.images],
              "scope": "session.run only; preloaded tensors; batch=1; after warmup",
              "latency_ms": {"mean": float(np.mean(timings)), "p50": float(np.percentile(timings, 50)),
                             "p95": float(np.percentile(timings, 95))},
              "model_only_fps": 1000 / float(np.mean(timings)), "samples_ms": timings}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples_ms"}, indent=2))


if __name__ == "__main__":
    main()
