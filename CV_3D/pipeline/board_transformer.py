import numpy as np
import cv2
from typing import Tuple, List, Dict
from .types import Detection


class BoardTransformer:
    """Выпрямляет доску по 4 углам с помощью Perspective Transform."""

    def __init__(self, output_size: int = 900, padding: int = 50):
        self.output_size = output_size
        self.padding = padding
        self.total_size = output_size + 2 * padding

    def get_ordered_corners(
        self,
        corners: Dict[int, Detection],
        img_width: int,
        img_height: int,
    ) -> Tuple[List[np.ndarray], bool]:
        """
        Определяет порядок углов для Perspective Transform.
        
        Args:
            corners: dict {class_id: Detection}
            img_width: ширина изображения
            img_height: высота изображения
            
        Returns:
            (ordered_points, white_at_bottom)
            ordered_points: [top_left, top_right, bottom_right, bottom_left]
        """
        def to_pixels(det: Detection) -> np.ndarray:
            x = det.x_center * img_width
            y = det.y_center * img_height
            return np.array([x, y], dtype=np.float32)

        white_left = to_pixels(corners[12])
        white_right = to_pixels(corners[13])
        black_left = to_pixels(corners[14])
        black_right = to_pixels(corners[15])

        # Порядок: [top_left, top_right, bottom_right, bottom_left]
        ordered = [black_right, black_left, white_left, white_right]
        white_at_bottom = True

        return ordered, white_at_bottom

    def transform(
        self,
        image: np.ndarray,
        corners: List[np.ndarray],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Применяет Perspective Transform.
        
        Returns:
            (warped_image, transform_matrix)
        """
        src_points = np.float32(corners)

        dst_points = np.float32([
            [self.output_size + self.padding, self.padding],
            [self.padding, self.padding],
            [self.output_size + self.padding, self.output_size + self.padding],
            [self.padding, self.output_size + self.padding],
        ])

        M = cv2.getPerspectiveTransform(src_points, dst_points)
        warped = cv2.warpPerspective(image, M, (self.total_size, self.total_size))

        return warped, M

    def transform_point(
        self,
        point: Tuple[float, float],
        matrix: np.ndarray,
    ) -> Tuple[float, float]:
        """Трансформирует одну точку (x_px, y_px) через матрицу M."""
        pt = np.float32([[[point[0], point[1]]]])
        transformed = cv2.perspectiveTransform(pt, matrix)
        return tuple(transformed[0][0])