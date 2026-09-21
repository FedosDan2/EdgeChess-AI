"""CPU backend: reuse the conversion pipeline's letterbox and class-aware NMS."""
import io
import json
import os
from pathlib import Path
import sys
from time import perf_counter

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from convert.common import postprocess, preprocess_image, sha256  # noqa: E402


class Detector:
    def __init__(self):
        self.path = Path(os.getenv("EDGECHESS_MODEL", ROOT / "convert/artifacts/yolov8s.onnx"))
        metadata_path = Path(os.getenv("EDGECHESS_METADATA", ROOT / "convert/artifacts/model.json"))
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.digest = sha256(self.path)
        if self.digest != self.metadata["onnx_sha256"]:
            raise ValueError("ONNX hash differs from model.json; export matching artifacts first")
        self.names = self.metadata["names"]
        self.size = self.metadata["imgsz"]
        self.threads = int(os.getenv("EDGECHESS_THREADS", "4"))
        if self.threads < 1:
            raise ValueError("EDGECHESS_THREADS must be positive")
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(self.path), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        if self.session.get_inputs()[0].shape != [1, 3, self.size, self.size]:
            raise ValueError("Expected static batch-1 NCHW ONNX")
        self.warmup_runs = 5
        for _ in range(self.warmup_runs):
            self.run_tensor(np.zeros((1, 3, self.size, self.size), dtype=np.float32))

    def run_tensor(self, tensor):
        return self.session.run(None, {self.input_name: tensor})[0]

    def describe(self):
        return {"model": self.path.name, "sha256": self.digest, "provider": "CPUExecutionProvider",
                "threads": self.threads, "input_size": self.size, "classes": self.names,
                "warmup_runs": self.warmup_runs, "confidence": .25, "nms_iou": .7}

    def predict(self, jpeg):
        start = perf_counter()
        # Check dimensions before allocating the decoded pixel buffer.
        with Image.open(io.BytesIO(jpeg)) as header:
            width, height = header.size
            if header.format != "JPEG" or not (1 <= width <= 1920 and 1 <= height <= 1920):
                raise ValueError("Expected JPEG up to 1920x1920")
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Cannot decode JPEG")
        _, _, tensor, info = preprocess_image(image, self.size)
        prepared = perf_counter()
        prediction = self.run_tensor(tensor)
        inferred = perf_counter()
        detections = postprocess(prediction, info, self.names)
        ended = perf_counter()
        return {"width": width, "height": height, "detections": detections,
                "timings": {"preprocess_ms": (prepared-start)*1000,
                            "inference_ms": (inferred-prepared)*1000,
                            "postprocess_ms": (ended-inferred)*1000,
                            "processing_ms": (ended-start)*1000}}
