import cv2
import numpy as np
from typing import Tuple


class ImagePreprocessor:
    """Предобработка изображения перед инференсом."""

    def __init__(self, target_size: Tuple[int, int] = (1024, 1024)):
        self.target_size = target_size

    def load_image(self, image_path: str) -> np.ndarray:
        """Загружает изображение."""
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        return img

    def resize(self, image: np.ndarray) -> np.ndarray:
        """Ресайзит изображение до target_size."""
        return cv2.resize(image, self.target_size, interpolation=cv2.INTER_AREA)

    def normalize(self, image: np.ndarray) -> np.ndarray:
        """Нормализует изображение (опционально)."""
        return image / 255.0

    def preprocess(self, image_path: str) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Полный цикл предобработки.
        
        Returns:
            (preprocessed_image, original_size)
        """
        img = self.load_image(image_path)
        original_size = (img.shape[1], img.shape[0])  # (width, height)
        
        # Если нужно ресайзить
        if img.shape[:2] != (self.target_size[1], self.target_size[0]):
            img = self.resize(img)
        
        return img, original_size