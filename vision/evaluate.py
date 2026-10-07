"""ChessRender360 placement checks on held-out RGB/JSON pairs.

The inferred-cell score includes missing corners; oracle geometry separates
point-to-cell errors from model errors. Simulator reports reuse the same geometry.
"""

import argparse
import json
from pathlib import Path
import cv2
from convert.common import images, save_json, compare_detections
from .config import ROOT, piece_symbol
from .geometry import board_geometry, placement
from .pipeline import Pipeline


def annotation_detections(annotation):
    detections = [
        {"class_name": p["piece_name"], "confidence": 1.0, "xyxy": p["bbox"]}
        for p in annotation["pieces"]
    ]
    for name, (x, y) in annotation["board_corners"].items():
        detections.append(
            {
                "class_name": "corner_" + name,
                "confidence": 1.0,
                "xyxy": [x - 1, y - 1, x + 1, y + 1],
            }
        )
    return detections


def cells(fen):
    if fen is None:
        return {}
    result = {}
    for row, line in enumerate(fen.split("/")):
        col = 0
        for ch in line:
            if ch.isdigit():
                col += int(ch)
            else:
                result[f"{'abcdefgh'[col]}{8 - row}"] = ch
                col += 1
    return result


def evaluate_2d(backend, confidence, output):
    pipeline = Pipeline("2d", backend, confidence=confidence)
    names = pipeline.models["pieces2d"].names
    rows = []
    try:
        for path in images(model="pieces2d"):
            image = cv2.imread(str(path))
            h, w = image.shape[:2]
            labels = path.parent.parent / "labels" / (path.stem + ".txt")
            truth = []
            for line in labels.read_text().splitlines():
                if not line.strip():
                    continue
                cls, x, y, bw, bh = map(float, line.split())
                truth.append(
                    {
                        "confidence": 1.0,
                        "class_id": int(cls),
                        "class_name": names[int(cls)],
                        "xyxy": [
                            (x - bw / 2) * w,
                            (y - bh / 2) * h,
                            (x + bw / 2) * w,
                            (y + bh / 2) * h,
                        ],
                    }
                )
            result = pipeline.predict(image)
            actual = [
                d for d in result["detections"] if d["class_name"] != "chessboard"
            ]
            rows.append(
                {
                    "image": path.name,
                    "status": result["status"],
                    "placement": result["placement"],
                    "agreement": compare_detections(truth, actual, min_iou=0.5),
                }
            )
    finally:
        pipeline.close()
    matched = sum(r["agreement"]["matched"] for r in rows)
    total = sum(r["agreement"]["reference_count"] for r in rows)
    detected = sum(r["agreement"]["actual_count"] for r in rows)
    report = {
        "profile": "2d",
        "backend": backend,
        "confidence": confidence,
        "frames": len(rows),
        "geometry_found": sum(r["placement"] is not None for r in rows),
        "matched": matched,
        "annotated_pieces": total,
        "precision": matched / detected if detected else 0,
        "recall": matched / total if total else 0,
        "note": "Complete board-crop-pieces cascade against YOLO labels on selected Roboflow v4 test images at IoU>=0.5; not mAP. Original training version/split of checkpoint not proven. Grid/FEN truth is not present in this dataset.",
        "images": rows,
    }
    save_json(
        output or ROOT / f"convert/artifacts/pieces2d/cascade_{backend}.json", report
    )
    print(json.dumps({k: v for k, v in report.items() if k != "images"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("2d", "3d"), default="3d")
    parser.add_argument(
        "--backend", choices=("onnx", "rknn_fp16", "rknn_int8"), default="onnx"
    )
    parser.add_argument(
        "--simulation", type=Path, help="Use detections from a Toolkit2 comparison.json"
    )
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.profile == "2d":
        if args.simulation:
            parser.error(
                "2D simulator reports are model-only; use ONNX or real RKNN NPU for the full cascade"
            )
        return evaluate_2d(args.backend, args.confidence, args.output)
    pipeline = (
        None
        if args.simulation
        else Pipeline("3d", args.backend, confidence=args.confidence)
    )
    simulated = (
        {
            r["image"]: r["detections"]
            for r in json.loads(args.simulation.read_text())["images"]
        }
        if args.simulation
        else {}
    )
    rows = []
    try:
        for path in images(model="chess3d"):
            a = json.loads(
                (
                    path.parent.parent
                    / "annotations"
                    / f"annotation_{path.stem[4:]}.json"
                ).read_text()
            )
            truth = {
                p["position"]["name"]: piece_symbol(p["piece_name"])
                for p in a["pieces"]
            }
            oracle = annotation_detections(a)
            matrix, _, _ = board_geometry(oracle, "3d")
            oracle_fen, _, _ = placement(oracle, matrix, "3d")
            if args.simulation:
                detections = [
                    d
                    for d in simulated[path.name]
                    if d["confidence"] >= args.confidence
                ]
                matrix, _, status = board_geometry(detections, "3d")
                fen, _, warnings = (
                    placement(detections, matrix, "3d")
                    if matrix is not None
                    else (None, [], [])
                )
                result = {"placement": fen, "status": status, "warnings": warnings}
            else:
                result = pipeline.predict(cv2.imread(str(path)))
            actual = cells(result["placement"])
            all_squares = [f"{f}{rank}" for f in "abcdefgh" for rank in range(1, 9)]
            rows.append(
                {
                    "image": path.name,
                    "status": result["status"],
                    "placement": result["placement"],
                    "exact": actual == truth,
                    "correct_cells": sum(
                        actual.get(s) == truth.get(s) for s in all_squares
                    )
                    if result["placement"]
                    else 0,
                    "correct_occupied": sum(
                        actual.get(s) == v for s, v in truth.items()
                    ),
                    "occupied": len(truth),
                    "oracle_correct_occupied": sum(
                        cells(oracle_fen).get(s) == v for s, v in truth.items()
                    ),
                    "warnings": result["warnings"],
                }
            )
    finally:
        if pipeline:
            pipeline.close()
    report = {
        "backend": args.backend,
        "simulation": bool(args.simulation),
        "confidence": args.confidence,
        "note": "32 source test frames selected using the training script split; split/version equivalence to the actual checkpoint is not independently proven. This is a subset check, not mAP.",
        "frames": len(rows),
        "geometry_found": sum(r["placement"] is not None for r in rows),
        "exact_positions": sum(r["exact"] for r in rows),
        "cell_accuracy": sum(r["correct_cells"] for r in rows) / (64 * len(rows)),
        "occupied_accuracy": sum(r["correct_occupied"] for r in rows)
        / sum(r["occupied"] for r in rows),
        "oracle_occupied_accuracy": sum(r["oracle_correct_occupied"] for r in rows)
        / sum(r["occupied"] for r in rows),
        "images": rows,
    }
    destination = (
        args.output or ROOT / f"convert/artifacts/chess3d/placement_{args.backend}.json"
    )
    save_json(destination, report)
    print(json.dumps({k: v for k, v in report.items() if k != "images"}, indent=2))


if __name__ == "__main__":
    main()
