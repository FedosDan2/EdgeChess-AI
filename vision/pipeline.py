from pathlib import Path
from time import perf_counter
from .config import ROOT, PROFILES, BACKENDS, profile_models
from .inference import Model
from .geometry import board_geometry, placement, board_crop


class Pipeline:
    def __init__(
        self, profile="2d", backend="onnx", directory=None, threads=4, confidence=0.5, model=None
    ):
        if (
            profile not in PROFILES
            or backend not in BACKENDS
            or threads < 1
            or not (0 < confidence <= 1)
        ):
            raise ValueError("Invalid pipeline configuration")
        self.profile, self.backend, self.threads, self.confidence = (
            profile,
            backend,
            threads,
            confidence,
        )
        self.keys = profile_models(profile, model)
        self.models = {}
        try:
            for key in self.keys:
                self.models[key] = Model(
                    key, Path(directory or ROOT / "convert/artifacts"), backend, threads
                )
        except BaseException:
            self.close()
            raise

    def close(self):
        for model in self.models.values():
            model.close()
        self.models.clear()

    def describe(self):
        models = [m.describe() for m in self.models.values()]
        return {
            "profile": self.profile,
            "backend": self.backend,
            "provider": "CPUExecutionProvider"
            if self.backend == "onnx"
            else "RKNN NPU",
            "model": " + ".join(m["key"] for m in models),
            "models": models,
            "threads": self.threads,
            "input_size": models[0]["input_size"],
            "warmup_runs": 5,
            "confidence": self.confidence,
            "nms_iou": 0.7,
        }

    def predict(self, image, orientation="white"):
        start = perf_counter()
        h, w = image.shape[:2]
        key = self.keys[0]
        detections, timings = self.models[key].predict(image, self.confidence)
        stages = {key: dict(timings)}
        geometry_start = perf_counter()
        matrix, board, status = board_geometry(detections, self.profile, orientation)
        pieces, fen, warnings = [], None, []
        geometry_ms = (perf_counter() - geometry_start) * 1000
        if matrix is not None:
            if self.profile == "2d":
                crop, (x1, y1) = board_crop(image, board[0])
                detected, second = self.models["pieces2d"].predict(
                    crop, self.confidence
                )
                stages["pieces2d"] = second
                for metric in timings:
                    timings[metric] += second[metric]
                detections = board + [
                    {
                        **d,
                        "xyxy": [
                            d["xyxy"][0] + x1,
                            d["xyxy"][1] + y1,
                            d["xyxy"][2] + x1,
                            d["xyxy"][3] + y1,
                        ],
                    }
                    for d in detected
                    if d["class_name"] != "chessboard"
                ]
            geometry_start = perf_counter()
            fen, pieces, warnings = placement(detections, matrix, self.profile)
            geometry_ms += (perf_counter() - geometry_start) * 1000
            if warnings:
                status = "ambiguous"
        timings["postprocess_ms"] += geometry_ms
        timings["processing_ms"] = (perf_counter() - start) * 1000
        return {
            "width": w,
            "height": h,
            "profile": self.profile,
            "backend": self.backend,
            "status": status,
            "model": " + ".join(self.keys),
            "detections": detections,
            "corners": board,
            "pieces": pieces,
            "placement": fen,
            "warnings": warnings,
            "timings": timings,
            "stages": stages,
        }
