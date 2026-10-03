from pathlib import Path
from typing import List
from ultralytics import YOLO
from .types import Detection, CLASS_NAMES, PIECE_CLASS_IDS


class PiecesDetector:
    """Детектирует шахматные фигуры."""

    def __init__(self, weights_path: str, confidence_threshold: float = 0.5):
        if not Path(weights_path).exists():
            raise FileNotFoundError(f"Model weights not found: {weights_path}")
        
        self.model = YOLO(weights_path)
        self.confidence_threshold = confidence_threshold

    def detect_pieces(self, image_path: str) -> List[Detection]:
        """
        Запускает инференс и возвращает только фигуры.
        
        Returns:
            список Detection для фигур (class_id 0-11)
        """
        results = self.model.predict(
            source=image_path,
            conf=self.confidence_threshold,
            verbose=False,
        )

        pieces: List[Detection] = []
        if len(results) == 0 or results[0].boxes is None:
            return pieces

        boxes = results[0].boxes
        for i in range(len(boxes)):
            class_id = int(boxes.cls[i].item())
            
            if class_id in PIECE_CLASS_IDS:
                confidence = float(boxes.conf[i].item())
                xywhn = boxes.xywhn[i].cpu().numpy()

                pieces.append(Detection(
                    class_id=class_id,
                    class_name=CLASS_NAMES.get(class_id, f"unknown_{class_id}"),
                    confidence=confidence,
                    x_center=float(xywhn[0]),
                    y_center=float(xywhn[1]),
                    width=float(xywhn[2]),
                    height=float(xywhn[3]),
                ))

        return pieces