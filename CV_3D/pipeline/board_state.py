from typing import List, Optional
from dataclasses import dataclass, field
from .types import PlacedPiece, PIECE_TO_FEN


@dataclass
class BoardState:
    """Матрица 8x8 положения фигур на доске."""
    board: List[List[Optional[str]]] = field(
        default_factory=lambda: [[None] * 8 for _ in range(8)]
    )

    def clear(self):
        """Очищает доску."""
        self.board = [[None] * 8 for _ in range(8)]

    def place_piece(self, piece: PlacedPiece):
        """Размещает фигуру на доске."""
        self.board[piece.row][piece.col] = piece.class_name

    def get_piece(self, row: int, col: int) -> Optional[str]:
        """Возвращает имя фигуры на позиции (row, col)."""
        return self.board[row][col]

    def to_fen_rows(self) -> List[str]:
        """
        Преобразует доску в 8 строк для FEN.
        Каждая строка — это rank (8, 7, ..., 1).
        """
        fen_rows = []
        for row_idx in range(8):
            row_str = ""
            empty_count = 0

            for col_idx in range(8):
                piece = self.board[row_idx][col_idx]
                if piece is None:
                    empty_count += 1
                else:
                    if empty_count > 0:
                        row_str += str(empty_count)
                        empty_count = 0
                    row_str += PIECE_TO_FEN.get(piece, "?")

            if empty_count > 0:
                row_str += str(empty_count)

            fen_rows.append(row_str)

        return fen_rows

    def __str__(self):
        """Визуальное представление доски."""
        rows = []
        for i, row in enumerate(self.board):
            rank = 8 - i
            row_str = f"{rank} "
            for cell in row:
                if cell is None:
                    row_str += ". "
                else:
                    symbol = PIECE_TO_FEN.get(cell, "?")
                    row_str += f"{symbol} "
            rows.append(row_str)
        rows.append("  a b c d e f g h")
        return "\n".join(rows)