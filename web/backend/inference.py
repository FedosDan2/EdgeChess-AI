"""JPEG adapter around the shared chess pipelines."""

import io
import os
from pathlib import Path
import sys
from time import perf_counter
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from convert.common import preprocess_image  # public to existing benchmark/tests
from vision.pipeline import Pipeline
from vision.config import PROFILES, BACKENDS, DEFAULT_3D_MODEL, MODELS_3D, profile_models


class Detector:
    def __init__(self):
        self.directory = Path(
            os.getenv("EDGECHESS_ARTIFACTS", ROOT / "convert/artifacts")
        )
        self.threads = int(os.getenv("EDGECHESS_THREADS", "4"))
        self.confidence = float(os.getenv("EDGECHESS_CONFIDENCE", "0.5"))
        self.pipeline = None
        self.profile = None
        self.backend = None
        self.model = None
        self.default_3d_model = os.getenv("EDGECHESS_3D_MODEL", DEFAULT_3D_MODEL)
        self.configure(
            os.getenv("EDGECHESS_PROFILE", "3d"), os.getenv("EDGECHESS_BACKEND", "onnx")
        )

    def configure(self, profile, backend, model=None):
        if profile not in PROFILES or backend not in BACKENDS:
            raise ValueError("Unknown pipeline or backend")
        model = profile_models(profile, model or self.default_3d_model)[0] if profile == "3d" else None
        if self.pipeline is not None and (profile, backend, model) == (
            self.profile,
            self.backend,
            self.model,
        ):
            return
        self.close()
        self.pipeline = Pipeline(
            profile, backend, self.directory, self.threads, self.confidence, model=model
        )
        self.profile, self.backend = profile, backend
        self.model = model

    def close(self):
        if self.pipeline is not None:
            self.pipeline.close()
        self.pipeline = None

    def describe(self):
        result = (
            self.pipeline.describe()
            if self.pipeline
            else {
                "status": "unavailable",
                "profile": self.profile,
                "backend": self.backend,
            }
        )
        result["model_choices"] = {key: label for key, label in MODELS_3D.items()
                                   if (self.directory / key / "model.json").is_file()}
        return result

    def predict(self, jpeg, orientation="white"):
        start = perf_counter()
        with Image.open(io.BytesIO(jpeg)) as header:
            w, h = header.size
            if header.format != "JPEG" or not (1 <= w <= 4096 and 1 <= h <= 4096):
                raise ValueError("Expected JPEG up to 4096x4096")
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Cannot decode JPEG")
        decoded = perf_counter()
        result = self.pipeline.predict(image, orientation)
        result["timings"]["preprocess_ms"] += (decoded - start) * 1000
        result["timings"]["processing_ms"] = (perf_counter() - start) * 1000
        return result
