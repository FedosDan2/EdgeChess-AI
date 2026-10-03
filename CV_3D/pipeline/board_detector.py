from pathlib import Path
from typing import Dict, List
from ultralytics import YOLO
from .types import Detection, CLASS_NAMES, CORNER_CLASS_IDS


class BoardDetector:
    """Детектирует углы шахматной доски."""

    def __init__(self, weights_path: str, confidence_threshold: float = 0.5):
        if not Path(weights_path).exists():
            raise FileNotFoundError(f"Model weights not found: {weights_path}")
        
        self.model = YOLO(weights_path)
        self.confidence_threshold = confidence_threshold

    def detect_corners(self, image_path: str) -> Dict[int, Detection]:
        """
        Запускает инференс и возвращает только углы доски.
        
        Returns:
            dict {class_id: Detection} для углов 12, 13, 14, 15
        """
        results = self.model.predict(
            source=image_path,
            conf=self.confidence_threshold,
            verbose=False,
        )

        corners: Dict[int, Detection] = {}
        if len(results) == 0 or results[0].boxes is None:
            return corners

        boxes = results[0].boxes
        for i in range(len(boxes)):
            class_id = int(boxes.cls[i].item())
            
            if class_id in CORNER_CLASS_IDS:
                confidence = float(boxes.conf[i].item())
                xywhn = boxes.xywhn[i].cpu().numpy()

                corners[class_id] = Detection(
                    class_id=class_id,
                    class_name=CLASS_NAMES.get(class_id, f"unknown_{class_id}"),
                    confidence=confidence,
                    x_center=float(xywhn[0]),
                    y_center=float(xywhn[1]),
                    width=float(xywhn[2]),
                    height=float(xywhn[3]),
                )

        return corners

    def validate_corners(self, corners: Dict[int, Detection]) -> bool:
        """Проверяет наличие всех 4 углов."""
        required = {12, 13, 14, 15}
        return required.issubset(corners.keys())