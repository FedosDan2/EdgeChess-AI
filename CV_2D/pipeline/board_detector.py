from ultralytics import YOLO
from .types import BoardDetection


class BoardDetector:
    def __init__(self, model_path: str, conf: float = 0.5):
        self.model = YOLO(model_path)
        self.conf = conf

    def detect(self, image) -> BoardDetection:
        result = self.model.predict(image, conf=self.conf, verbose=False)[0]

        if len(result.boxes) == 0:
            raise RuntimeError("Chessboard not detected")

        box = result.boxes[0]

        return BoardDetection(
            bbox=tuple(box.xyxy[0].tolist()),
            confidence=float(box.conf[0])
        )