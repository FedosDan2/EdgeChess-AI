"""CPU smoke experiment: real YOLO ONNX plus official persistent Stockfish.

Not a model-quality evaluation or a Firefly/NPU performance claim.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "web")]
import chess
import cv2
import numpy as np
from backend.advisor import StockfishAdvisor
from vision.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/stockfish-cpu-experiment.json")
    args = parser.parse_args()
    if not 1 <= args.runs <= 1000:
        parser.error("runs must be 1..1000")
    image = cv2.imread(str(args.image))
    if image is None:
        parser.error("Cannot decode image")
    pipeline = Pipeline("3d", "onnx", model="chess3d_m")
    advisor = StockfishAdvisor()
    try:
        warm = advisor.best_move(chess.Board(), "experiment")
        assert chess.Move.from_uci(warm["move_uci"]) in chess.Board().legal_moves

        def measure(future=None):
            rows = []
            for _ in range(args.runs):
                overlaps = future is not None and not future.done()
                start = perf_counter()
                result = pipeline.predict(image)
                rows.append({"ms": (perf_counter() - start) * 1000,
                             "search_in_progress_at_start": overlaps,
                             "status": result["status"], "placement": result["placement"]})
            return {"mean_ms": float(np.mean([r["ms"] for r in rows])),
                    "p95_ms": float(np.percentile([r["ms"] for r in rows], 95)), "frames": rows}

        pipeline.predict(image)
        baseline = measure()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(advisor.best_move, chess.Board(), "experiment")
            concurrent = measure(future)
            advice = future.result()
        overlap_times = [r["ms"] for r in concurrent["frames"] if r["search_in_progress_at_start"]]
        assert chess.Move.from_uci(advice["move_uci"]) in chess.Board().legal_moves
        report = {"platform": platform.platform(), "python": platform.python_version(),
                  "note": "CPU smoke only; this image is not necessarily the engine's initial position. No accuracy or NPU claim.",
                  "image": args.image.name, "pipeline": pipeline.describe(),
                  "baseline": baseline, "concurrent": concurrent, "advice": advice,
                  "overlapping_frames": len(overlap_times),
                  "overlap_mean_ms": float(np.mean(overlap_times)) if overlap_times else None}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"baseline_mean_ms": baseline["mean_ms"],
                          "concurrent_mean_ms": concurrent["mean_ms"],
                          "overlapping_frames": report["overlapping_frames"],
                          "overlap_mean_ms": report["overlap_mean_ms"],
                          "advice": advice}, indent=2))
    finally:
        pipeline.close()
        advisor.close()


if __name__ == "__main__":
    main()
