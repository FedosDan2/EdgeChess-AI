class SquareMapper:
    FILES = "abcdefgh"

    def __init__(self, board_size, orientation):
        self.width, self.height = board_size
        self.orientation = orientation

    def get_square(self, bbox):
        x1, y1, x2, y2 = bbox

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        col = int(cx / (self.width / 8))
        row = int(cy / (self.height / 8))

        col = max(0, min(7, col))
        row = max(0, min(7, row))

        if self.orientation == 1:
            file = self.FILES[col]
            rank = 8 - row
        else:
            file = self.FILES[7 - col]
            rank = row + 1

        return f"{file}{rank}"