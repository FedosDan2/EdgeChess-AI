"""Independent regression check against Ultralytics' NMS and LetterBox.

Uses actual test images and artificial landscape/portrait images. This guards
against a shared preprocessing/NMS bug making both ONNX comparisons look correct.
"""
import json
import os
import tempfile
from pathlib import Path

from common import ARTIFACTS, compare_detections, images, postprocess, preprocess
os.environ.setdefault("YOLO_CONFIG_DIR", str(ARTIFACTS / "ultralytics"))
import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics.data.augment import LetterBox
from ultralytics.utils.ops import non_max_suppression, scale_boxes


def main():
    metadata = json.loads((ARTIFACTS / "model.json").read_text(encoding="utf-8"))
    # Cover non-square inputs; source Kaggle samples happen to be square.
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
        for h, w in [(720, 1280), (1280, 720), (517, 883)]:
            image = np.random.default_rng(42).integers(0, 256, size=(h, w, 3), dtype=np.uint8)
            path = Path(directory) / "input.png"
            if not cv2.imwrite(str(path), image):
                raise ValueError(f"Cannot write test image: {path}")
            _, rgb, _, _ = preprocess(path)
            expected = LetterBox(new_shape=(640, 640), auto=False)(image=image)
            np.testing.assert_array_equal(rgb, cv2.cvtColor(expected, cv2.COLOR_BGR2RGB))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(ARTIFACTS / "yolov8s.onnx"), sess_options=options,
                                   providers=["CPUExecutionProvider"])
    for path in images():
        original, rgb, tensor, info = preprocess(path)
        expected_rgb = cv2.cvtColor(LetterBox(new_shape=(640, 640), auto=False)(image=original), cv2.COLOR_BGR2RGB)
        np.testing.assert_array_equal(rgb, expected_rgb)
        prediction = session.run(None, {"images": tensor})[0]
        custom = postprocess(prediction, info, metadata["names"])
        official = non_max_suppression(torch.from_numpy(prediction.copy()), conf_thres=.25,
                                       iou_thres=.7, nc=len(metadata["names"]))[0]
        official[:, :4] = scale_boxes((640, 640), official[:, :4], original.shape[:2],
                                      ratio_pad=((info["ratio"], info["ratio"]), (info["left"], info["top"])))
        reference = [{"xyxy": row[:4].tolist(), "confidence": float(row[4]), "class_id": int(row[5])}
                     for row in official.numpy()]
        agreement = compare_detections(reference, custom, min_iou=.999)
        assert agreement["missing"] == 0 and agreement["extra"] == 0, (path, agreement)
    print("PASS: custom LetterBox matches Ultralytics on 3 aspect ratios and all test images")
    print("PASS: custom NMS and coordinate restoration match Ultralytics on all test images")


if __name__ == "__main__":
    main()
