from .board_state import BoardState


class FENBuilder:
    """Строит FEN-строку из состояния доски."""

    def __init__(self, active_color: str = "w"):
        """
        Args:
            active_color: 'w' или 'b' — чей ход
        """
        self.active_color = active_color

    def build(self, board_state: BoardState) -> str:
        """
        Генерирует полную FEN-строку.
        
        Формат:
        <piece placement> <active color> <castling> <en passant> <halfmove> <fullmove>
        """
        # 1. Расположение фигур
        piece_placement = "/".join(board_state.to_fen_rows())

        # 2. Активный цвет
        active_color = self.active_color

        # 3. Рокировка (пока нет информации — ставим '-')
        castling = "-"

        # 4. Взятие на проходе (пока '-')
        en_passant = "-"

        # 5. Половинный ход (для правила 50 ходов)
        halfmove = "0"

        # 6. Полный ход
        fullmove = "1"

        fen = f"{piece_placement} {active_color} {castling} {en_passant} {halfmove} {fullmove}"
        return fen

    def set_active_color(self, color: str):
        """Устанавливает активный цвет ('w' или 'b')."""
        if color not in ("w", "b"):
            raise ValueError("active_color must be 'w' or 'b'")
        self.active_color = color