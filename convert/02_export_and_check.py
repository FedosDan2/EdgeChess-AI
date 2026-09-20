"""CPU: load trusted YOLOv8 detection checkpoint, export two ONNX graphs, compare.

Standard ONNX preserves decoded xywh output. Split ONNX moves only DFL/coordinate
decoding to common.py for RKNN; weights and convolutional layers are unchanged.
Every image is run through original PyTorch, standard ONNX and decoded split ONNX.
"""
import argparse
import importlib.metadata
import os
import platform
import time
import types

from common import ARTIFACTS, ROOT, compare_detections, decode_split, draw, images, postprocess, preprocess, save_json, sha256

os.environ.setdefault("YOLO_CONFIG_DIR", str(ARTIFACTS / "ultralytics"))
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
import numpy as np
import onnx
import onnxruntime as ort
import torch
from ultralytics import YOLO


def split_head(self, features):
    outputs = []
    for index in range(self.nl):
        outputs.extend((self.cv2[index](features[index]), self.cv3[index](features[index]).sigmoid()))
    return tuple(outputs)


def export(model, path, outputs):
    dummy = torch.zeros(1, 3, 640, 640)
    with torch.inference_mode():
        model(dummy)
        torch.onnx.export(model, dummy, str(path), input_names=["images"], output_names=outputs,
                          opset_version=12, do_constant_folding=True, dynamic_axes=None)
    onnx.checker.check_model(str(path))


def session(path, threads):
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default=str(ROOT.parent / "YOLOv8s_test.pt"))
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    ARTIFACTS.mkdir(exist_ok=True)
    torch.set_num_threads(args.threads)
    yolo = YOLO(args.weights, task="detect")
    network = yolo.model.cpu().float().eval()
    head = network.model[-1]
    if type(head).__name__ != "Detect" or head.nl != 3 or getattr(head, "end2end", False):
        raise ValueError("This script supports the three-scale YOLOv8 Detect head only")
    names = [network.names[i] for i in range(head.nc)]
    print(f"Classes ({len(names)}): {names}", flush=True)
    network.fuse()
    head.export, head.format, head.dynamic = True, "onnx", False
    standard_path, split_path = ARTIFACTS / "yolov8s.onnx", ARTIFACTS / "yolov8s_split.onnx"
    print("Exporting standard ONNX (opset 12, static NCHW, external NMS)", flush=True)
    export(network, standard_path, ["predictions"])
    original_forward = head.forward
    head.forward = types.MethodType(split_head, head)
    print("Exporting split-head ONNX (DFL decode moved to CPU)", flush=True)
    try:
        export(network, split_path, [f"{kind}_{stride}" for stride in (8, 16, 32) for kind in ("boxes", "scores")])
    finally:
        head.forward = original_forward
    standard, split = session(standard_path, args.threads), session(split_path, args.threads)
    manifest = {"weights_sha256": sha256(args.weights), "names": names, "imgsz": 640, "opset": 12,
                "reg_max": head.reg_max, "strides": head.stride.tolist(),
                "preprocessing": {"color": "RGB", "letterbox": 640, "pad": 114,
                                  "onnx_layout": "NCHW", "onnx_dtype": "float32", "onnx_scale": "1/255",
                                  "rknn_layout": "NHWC", "rknn_dtype": "uint8", "rknn_std": 255},
                "postprocessing": {"confidence": .25, "nms_iou": .7, "class_aware": True},
                "onnx_sha256": sha256(standard_path), "split_onnx_sha256": sha256(split_path),
                "split_outputs": [{"name": o.name, "shape": o.shape} for o in split.get_outputs()],
                "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                **{p: importlib.metadata.version(p) for p in
                                   ("torch", "ultralytics", "onnx", "onnxruntime", "numpy", "opencv-python")}}}
    save_json(ARTIFACTS / "model.json", manifest)
    baseline, comparisons = {}, []
    # Warm up before timing; these are local CPU call durations, not NPU benchmarks.
    dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
    with torch.inference_mode():
        network(torch.from_numpy(dummy))
    standard.run(None, {"images": dummy})
    split.run(None, {"images": dummy})
    all_passed = True
    for path in images():
        image, _, tensor, info = preprocess(path)
        begin = time.perf_counter()
        with torch.inference_mode():
            expected = network(torch.from_numpy(tensor)).numpy()
        torch_ms = (time.perf_counter() - begin) * 1000
        begin = time.perf_counter()
        actual = standard.run(None, {"images": tensor})[0]
        onnx_ms = (time.perf_counter() - begin) * 1000
        split_prediction = decode_split(split.run(None, {"images": tensor}))
        reference = postprocess(expected, info, names)
        baseline[path.name] = {"image_sha256": sha256(path), "detections": reference}
        draw(image, reference, ARTIFACTS / "pytorch" / path.name)
        record = {"image": path.name, "pytorch_cpu_ms": torch_ms, "onnx_cpu_ms": onnx_ms}
        for label, prediction in [("onnx", actual), ("split_onnx", split_prediction)]:
            detections = postprocess(prediction, info, names)
            boxes_ok = bool(np.allclose(expected[:, :4], prediction[:, :4], atol=.02, rtol=1e-4))
            scores_ok = bool(np.allclose(expected[:, 4:], prediction[:, 4:], atol=2e-5, rtol=1e-4))
            agreement = compare_detections(reference, detections, min_iou=.99)
            passed = boxes_ok and scores_ok and agreement["missing"] == 0 and agreement["extra"] == 0
            all_passed &= passed
            record[label] = {"passed": passed, "max_box_delta": float(np.max(np.abs(expected[:, :4] - prediction[:, :4]))),
                             "max_score_delta": float(np.max(np.abs(expected[:, 4:] - prediction[:, 4:]))),
                             "agreement": agreement}
            draw(image, detections, ARTIFACTS / label / path.name)
        comparisons.append(record)
        print(f"{path.name}: {len(reference)} detections; ONNX={record['onnx']['passed']}, split={record['split_onnx']['passed']}", flush=True)
    save_json(ARTIFACTS / "pytorch_predictions.json", baseline)
    save_json(ARTIFACTS / "onnx_comparison.json", {"passed": all_passed, "image_count": len(comparisons),
              "note": "Agreement with PyTorch on a small subset; not ground-truth mAP or an NPU benchmark.",
              "model": manifest, "images": comparisons})
    if not comparisons or not all_passed:
        raise SystemExit("ONNX verification FAILED; inspect artifacts/onnx_comparison.json")
    print("ONNX verification PASSED", flush=True)


if __name__ == "__main__":
    main()
