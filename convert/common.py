"""Shared, explicit image preprocessing and YOLOv8 decoding (no hidden predictor).

ONNX/PyTorch receive RGB float32 NCHW in [0, 1]. RKNN receives the same
letterboxed RGB image as uint8 NHWC; its configured std=255 normalizes once.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def images(split="test"):
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    return [ROOT / r["path"] for r in manifest["files"]
            if r["path"].startswith(f"data/{split}/images/")]


def preprocess(path, size=640):
    original = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if original is None:
        raise ValueError(f"Cannot decode {path}")
    height, width = original.shape[:2]
    ratio = min(size / height, size / width)
    resized = cv2.resize(original, (round(width * ratio), round(height * ratio)), interpolation=cv2.INTER_LINEAR)
    dw, dh = size - resized.shape[1], size - resized.shape[0]
    left, top = dw // 2, dh // 2
    padded = cv2.copyMakeBorder(resized, top, dh - top, left, dw - left,
                               cv2.BORDER_CONSTANT, value=(114, 114, 114))
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    return original, rgb, tensor, {"ratio": ratio, "left": left, "top": top,
                                  "height": height, "width": width}


def decode_split(outputs, size=640):
    """Six outputs: (box DFL logits, class probabilities) for strides 8/16/32.

    Softmax over reg_max bins followed by expectation is YOLOv8's DFL decoder.
    Produces the same [1, 4+nc, 8400] xywh/probability tensor as standard export.
    """
    if len(outputs) != 6:
        raise ValueError(f"Expected six split-head outputs, got {len(outputs)}")
    decoded = []
    for index in range(0, 6, 2):
        regression, scores = outputs[index:index + 2]
        batch, channels, height, width = regression.shape
        if batch != 1 or channels % 4 or scores.shape[0] != 1 or scores.shape[2:] != (height, width):
            raise ValueError("Unexpected YOLOv8 output layout")
        bins = channels // 4
        logits = regression.reshape(1, 4, bins, height, width)
        probabilities = np.exp(logits - logits.max(axis=2, keepdims=True))
        probabilities /= probabilities.sum(axis=2, keepdims=True)
        distances = (probabilities * np.arange(bins, dtype=np.float32)[None, None, :, None, None]).sum(axis=2)
        gy, gx = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
        center = np.stack((gx + .5, gy + .5))[None].astype(np.float32)
        minimum = center - distances[:, :2]
        maximum = center + distances[:, 2:]
        xywh = np.concatenate(((minimum + maximum) / 2, maximum - minimum), axis=1) * (size / height)
        decoded.append(np.concatenate((xywh, scores), axis=1).reshape(1, 4 + scores.shape[1], -1))
    return np.concatenate(decoded, axis=2)


def box_iou(box, boxes):
    intersection = np.maximum(0, np.minimum(box[2:], boxes[:, 2:]) - np.maximum(box[:2], boxes[:, :2])).prod(axis=1)
    area1 = np.maximum(0, box[2:] - box[:2]).prod()
    area2 = np.maximum(0, boxes[:, 2:] - boxes[:, :2]).prod(axis=1)
    return intersection / np.maximum(area1 + area2 - intersection, 1e-9)


def postprocess(prediction, info, names, confidence=.25, nms_iou=.7):
    if prediction.shape[0] != 1 or prediction.shape[1] != 4 + len(names):
        raise ValueError(f"Unexpected prediction shape {prediction.shape}")
    candidates = prediction[0].T
    classes = candidates[:, 4:].argmax(axis=1)
    scores = candidates[:, 4:].max(axis=1)
    valid = scores >= confidence
    xywh, classes, scores = candidates[valid, :4], classes[valid], scores[valid]
    boxes = np.concatenate((xywh[:, :2] - xywh[:, 2:] / 2, xywh[:, :2] + xywh[:, 2:] / 2), axis=1)
    order = scores.argsort()[::-1]
    kept = []
    while len(order) and len(kept) < 300:
        current, remaining = order[0], order[1:]
        kept.append(current)
        suppress = (classes[remaining] == classes[current]) & (box_iou(boxes[current], boxes[remaining]) > nms_iou)
        order = remaining[~suppress]
    result = []
    for index in kept:
        box = boxes[index].copy()
        box[[0, 2]] = np.clip((box[[0, 2]] - info["left"]) / info["ratio"], 0, info["width"])
        box[[1, 3]] = np.clip((box[[1, 3]] - info["top"]) / info["ratio"], 0, info["height"])
        result.append({"class_id": int(classes[index]), "class_name": names[int(classes[index])],
                       "confidence": float(scores[index]), "xyxy": box.tolist()})
    return result


def draw(image, detections, path):
    canvas = image.copy()
    for detection in detections:
        x1, y1, x2, y2 = map(round, detection["xyxy"])
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 200, 0), 2)
        cv2.putText(canvas, f'{detection["class_name"]} {detection["confidence"]:.2f}',
                    (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 80, 255), 1, cv2.LINE_AA)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    success, buffer = cv2.imencode(".jpg", canvas)
    if not success:
        raise ValueError("Cannot encode annotated image")
    buffer.tofile(path)


def compare_detections(reference, actual, min_iou=.9):
    """Greedy class-aware matching; agreement with a baseline, NOT ground-truth mAP."""
    unused = set(range(len(actual)))
    pairs = []
    for expected in reference:
        candidates = [i for i in unused if actual[i]["class_id"] == expected["class_id"]]
        if not candidates:
            continue
        overlaps = box_iou(np.array(expected["xyxy"]), np.array([actual[i]["xyxy"] for i in candidates]))
        best = int(overlaps.argmax())
        if overlaps[best] >= min_iou:
            index = candidates[best]
            unused.remove(index)
            pairs.append({"iou": float(overlaps[best]),
                          "confidence_delta": abs(expected["confidence"] - actual[index]["confidence"])})
    return {"reference_count": len(reference), "actual_count": len(actual), "matched": len(pairs),
            "missing": len(reference) - len(pairs), "extra": len(unused),
            "min_matched_iou": min((p["iou"] for p in pairs), default=None),
            "max_confidence_delta": max((p["confidence_delta"] for p in pairs), default=None)}
