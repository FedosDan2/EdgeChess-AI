class FENBuilder:
    PIECES = {
        "w-king": "K",
        "w-queen": "Q",
        "w-rook": "R",
        "w-bishop": "B",
        "w-knight": "N",
        "w-pawn": "P",
        "b-king": "k",
        "b-queen": "q",
        "b-rook": "r",
        "b-bishop": "b",
        "b-knight": "n",
        "b-pawn": "p",
    }

    def build(self, board_state):
        rows = []

        for row in board_state.board:
            fen_row = ""
            empty = 0

            for piece in row:
                if piece is None:
                    empty += 1
                else:
                    if empty:
                        fen_row += str(empty)
                        empty = 0

                    fen_row += self.PIECES[piece]

            if empty:
                fen_row += str(empty)

            rows.append(fen_row)

        return "/".join(rows)