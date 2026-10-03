from ultralytics import YOLO
from .types import PieceDetection

class PiecesDetector:
    def __init__(self, model_path: str, conf: float = 0.5):
        self.model = YOLO(model_path)
        self.conf = conf

    def detect(self, image):
        result = self.model.predict(image, conf=self.conf, verbose=False)[0]

        pieces = []

        for box in result.boxes:
            cls_id = int(box.cls[0])

            if cls_id == 0:
                continue

            pieces.append(
                PieceDetection(
                    name=self.model.names[cls_id],
                    confidence=float(box.conf[0]),
                    bbox=tuple(box.xyxy[0].tolist())
                )
            )

        return pieces