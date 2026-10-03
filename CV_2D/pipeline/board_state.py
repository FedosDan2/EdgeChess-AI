class BoardState:
    def __init__(self):
        self.board = [[None for _ in range(8)] for _ in range(8)]

    def set_piece(self, square, piece):
        col = ord(square[0]) - ord("a")
        row = 8 - int(square[1])

        self.board[row][col] = piece

    def from_pieces(self, pieces):
        self.board = [[None for _ in range(8)] for _ in range(8)]

        for piece in pieces:
            if piece.square:
                self.set_piece(piece.square, piece.name)

        return self

    def __str__(self):
        return "\n".join(str(row) for row in self.board)