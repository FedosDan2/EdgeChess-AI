"""Linux/Python 3.10: build RKNN and test it with Toolkit2's CPU simulator.

Run twice in separate processes: --precision fp16 and --precision int8.
The simulator is initialized on the built object, not via load_rknn().
Simulation validates numerical behavior; it is NOT an NPU performance test.
"""
import argparse
import importlib.metadata
import json
import os
import platform
import time

import numpy as np
from rknn.api import RKNN
from common import ARTIFACTS, ROOT, compare_detections, decode_split, draw, images, postprocess, preprocess, save_json, sha256


def check(status, operation):
    if status != 0:
        raise RuntimeError(f"{operation} failed, RKNN status={status}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=("fp16", "int8"), required=True)
    parser.add_argument("--limit", type=int, default=0, help="0: all selected test images")
    args = parser.parse_args()
    os.chdir(ROOT)
    manifest = json.loads((ARTIFACTS / "model.json").read_text(encoding="utf-8"))
    baseline = json.loads((ARTIFACTS / "pytorch_predictions.json").read_text(encoding="utf-8"))
    model_path = ARTIFACTS / "yolov8s_split.onnx"
    if sha256(model_path) != manifest["split_onnx_sha256"]:
        raise ValueError("ONNX hash differs from the verified model")
    quantized = args.precision == "int8"
    out = ARTIFACTS / f"rknn_{args.precision}"
    out.mkdir(exist_ok=True)
    rknn = RKNN(verbose=True, verbose_file=str(out / "build.log"))
    started = time.perf_counter()
    try:
        print("Config: rk3588, RGB uint8, normalization inside RKNN: divide by 255", flush=True)
        check(rknn.config(target_platform="rk3588", mean_values=[[0, 0, 0]],
                          std_values=[[255, 255, 255]]), "config")
        check(rknn.load_onnx(model=str(model_path)), "load_onnx")
        kwargs = {"do_quantization": quantized}
        if quantized:
            kwargs["dataset"] = str(ROOT / "data/calibration.txt")
        check(rknn.build(**kwargs), "build")
        rknn_path = out / "model.rknn"
        check(rknn.export_rknn(str(rknn_path)), "export_rknn")
        build_seconds = time.perf_counter() - started
        check(rknn.init_runtime(), "init_runtime simulator")
        selected = images()[:args.limit] if args.limit else images()
        rows = []
        for path in selected:
            if sha256(path) != baseline[path.name]["image_sha256"]:
                raise ValueError(f"Test image changed: {path}")
            original, rgb, _, info = preprocess(path)
            outputs = rknn.inference(inputs=[rgb[None]], data_format=["nhwc"])
            prediction = decode_split(outputs)
            if not np.isfinite(prediction).all():
                raise ValueError("Simulator returned NaN/Inf")
            detections = postprocess(prediction, info, manifest["names"])
            agreement = compare_detections(baseline[path.name]["detections"], detections, min_iou=.9)
            rows.append({"image": path.name, "agreement": agreement, "detections": detections})
            draw(original, detections, out / "images" / path.name)
            print(f"{args.precision}: {path.name}: {agreement}", flush=True)
        reference_count = sum(r["agreement"]["reference_count"] for r in rows)
        actual_count = sum(r["agreement"]["actual_count"] for r in rows)
        matched = sum(r["agreement"]["matched"] for r in rows)
        recall = matched / reference_count if reference_count else 0
        precision = matched / actual_count if actual_count else 0
        # These thresholds check conversion drift, not the model's task accuracy.
        passed = bool(rows) and reference_count > 0 and recall >= .95 and precision >= .95
        save_json(out / "comparison.json", {"precision": args.precision, "passed": passed,
            "note": "Simulator only. Agreement with PyTorch at IoU>=0.9, confidence>=0.25; NOT ground-truth mAP.",
            "agreement_recall": recall, "agreement_precision": precision, "matched": matched,
            "reference_count": reference_count, "actual_count": actual_count,
            "build_seconds": build_seconds, "rknn_bytes": rknn_path.stat().st_size,
            "rknn_sha256": sha256(rknn_path), "onnx_sha256": sha256(model_path),
            "environment": {"python": platform.python_version(),
                            **{p: importlib.metadata.version(p) for p in ("rknn-toolkit2", "torch", "numpy")}},
            "images": rows})
        print(f"Simulator agreement: recall={recall:.4f}, precision={precision:.4f}; passed={passed}")
        if not passed:
            raise SystemExit("Conversion drift exceeds threshold; review comparison.json")
    finally:
        rknn.release()


if __name__ == "__main__":
    main()
