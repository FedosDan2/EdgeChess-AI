from dataclasses import dataclass
from typing import Optional


# Маппинг ID классов в имена
CLASS_NAMES = {
    0: "white_queen",  1: "white_king",  2: "white_bishop",
    3: "white_knight", 4: "white_rook",  5: "white_pawn",
    6: "black_queen",  7: "black_king",  8: "black_bishop",
    9: "black_knight", 10: "black_rook", 11: "black_pawn",
    12: "corner_white_left",  13: "corner_white_right",
    14: "corner_black_left",  15: "corner_black_right",
}

# Маппинг имён классов в FEN-символы
PIECE_TO_FEN = {
    "white_queen": "Q", "white_king": "K", "white_bishop": "B",
    "white_knight": "N", "white_rook": "R", "white_pawn": "P",
    "black_queen": "q", "black_king": "k", "black_bishop": "b",
    "black_knight": "n", "black_rook": "r", "black_pawn": "p",
}

# ID классов
CORNER_CLASS_IDS = {12, 13, 14, 15}
PIECE_CLASS_IDS = set(range(12))


@dataclass
class Detection:
    """Результат детекции одного объекта."""
    class_id: int
    class_name: str
    confidence: float
    x_center: float  # нормализованные [0, 1]
    y_center: float
    width: float
    height: float

    @property
    def is_corner(self) -> bool:
        return self.class_id in CORNER_CLASS_IDS

    @property
    def is_piece(self) -> bool:
        return self.class_id in PIECE_CLASS_IDS


@dataclass
class PlacedPiece:
    """Фигура, размещённая на клетке."""
    class_name: str
    cell: str  # например, "e4"
    confidence: float
    col: int   # 0-7 (a-h)
    row: int   # 0-7 (8-1 сверху вниз)