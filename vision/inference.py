"""ONNX and RKNN share preprocessing, DFL decoding and NMS."""

import json
from time import perf_counter
import numpy as np
from convert.common import preprocess_image, postprocess, decode_split, sha256


class Model:
    def __init__(self, key, directory, backend="onnx", threads=4):
        self.key, self.backend = key, backend
        self.directory = directory / key
        self.metadata = json.loads((self.directory / "model.json").read_text())
        self.names, self.size = self.metadata["names"], self.metadata["imgsz"]
        self.session = None
        self.conversion_verified = True
        if backend == "onnx":
            import onnxruntime as ort

            path = self.directory / "model.onnx"
            digest = self.metadata["onnx_sha256"]
            options = ort.SessionOptions()
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            if sha256(path) != digest:
                raise ValueError("ONNX hash differs from model.json")
            self.session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            inp = self.session.get_inputs()[0]
            if inp.shape != [1, 3, self.size, self.size]:
                raise ValueError("Expected static batch-1 NCHW ONNX")
            self.input_name = inp.name
        else:
            from rknnlite.api import RKNNLite

            path = self.directory / backend / "model.rknn"
            report = json.loads((path.parent / "comparison.json").read_text())
            if (
                report["onnx_sha256"] != self.metadata["split_onnx_sha256"]
                or sha256(path) != report["rknn_sha256"]
            ):
                raise ValueError("RKNN hash differs from verified artifacts")
            self.conversion_verified = report["passed"]
            self.session = RKNNLite(verbose=False)
            try:
                if self.session.load_rknn(str(path)) or self.session.init_runtime():
                    raise RuntimeError("Cannot initialize RKNN NPU runtime")
            except BaseException:
                self.close()
                raise
        self.path, self.digest = path, sha256(path)
        try:
            for _ in range(5):
                self.run(
                    np.zeros((1, 3, self.size, self.size), np.float32),
                    np.zeros((self.size, self.size, 3), np.uint8),
                )
        except BaseException:
            self.close()
            raise

    def run(self, tensor, rgb):
        if self.backend == "onnx":
            return self.session.run(None, {self.input_name: tensor})[0]
        outputs = self.session.inference(inputs=[rgb[None]], data_format=["nhwc"])
        return decode_split(outputs, self.size)

    def predict(self, image, confidence=0.5):
        start = perf_counter()
        _, rgb, tensor, info = preprocess_image(image, self.size)
        prepared = perf_counter()
        prediction = self.run(tensor, rgb)
        inferred = perf_counter()
        detections = postprocess(prediction, info, self.names, confidence=confidence)
        ended = perf_counter()
        return detections, {
            "preprocess_ms": (prepared - start) * 1000,
            "inference_ms": (inferred - prepared) * 1000,
            "postprocess_ms": (ended - inferred) * 1000,
        }

    def describe(self):
        return {
            "key": self.key,
            "model": self.path.name,
            "sha256": self.digest,
            "input_size": self.size,
            "classes": self.names,
            "conversion_verified": self.conversion_verified,
        }

    def close(self):
        if self.session is not None and self.backend != "onnx":
            self.session.release()
        self.session = None
