import cv2
import numpy as np
from typing import Tuple


class SquareMapper:
    """Рисует сетку и маппит пиксели в шахматные клетки."""

    def __init__(
        self,
        output_size: int = 900,
        padding: int = 50,
        color=(0, 255, 255),
        thickness: int = 1,
    ):
        self.output_size = output_size
        self.padding = padding
        self.color = color
        self.thickness = thickness
        self.cell_size = output_size / 8

    def draw_grid(self, image: np.ndarray, white_at_bottom: bool = True) -> np.ndarray:
        """Рисует сетку 8x8 и подписи."""
        img = image.copy()

        # Вертикальные линии
        for i in range(1, 8):
            x = int(self.padding + i * self.cell_size)
            cv2.line(img, (x, self.padding), (x, self.padding + self.output_size),
                     self.color, self.thickness)

        # Горизонтальные линии
        for i in range(1, 8):
            y = int(self.padding + i * self.cell_size)
            cv2.line(img, (self.padding, y), (self.padding + self.output_size, y),
                     self.color, self.thickness)

        # Подписи
        cols = "abcdefgh"
        for i in range(8):
            if white_at_bottom:
                # Буквы снизу (a-h)
                cv2.putText(img, cols[i],
                            (int(self.padding + i * self.cell_size + self.cell_size / 2 - 5),
                             self.padding + self.output_size + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.color, 1)
                # Цифры слева (1-8 снизу вверх)
                cv2.putText(img, str(i + 1),
                            (self.padding - 25,
                             int(self.padding + (7 - i) * self.cell_size + self.cell_size / 2 + 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.color, 1)
            else:
                cv2.putText(img, cols[len(cols) - i - 1],
                            (int(self.padding + i * self.cell_size + self.cell_size / 2 - 5),
                             self.padding - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.color, 1)
                cv2.putText(img, str(i + 1),
                            (self.padding - 25,
                             int(self.padding + i * self.cell_size + self.cell_size / 2 + 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.color, 1)

        return img

    def pixel_to_cell(self, x_px: float, y_px: float) -> Tuple[str, int, int]:
        """
        Переводит пиксельные координаты в шахматную нотацию.
        
        Returns:
            (cell_name, col, row)
            cell_name: например, 'e4'
            col: 0-7 (a-h)
            row: 0-7 (8-1 сверху вниз)
        """
        col = int((x_px - self.padding) / self.cell_size)
        row = int((y_px - self.padding) / self.cell_size)

        col = max(0, min(7, col))
        row = max(0, min(7, row))

        file_char = "abcdefgh"[col]
        rank = 8 - row
        cell_name = f"{file_char}{rank}"

        return cell_name, col, row