from .board_detector import BoardDetector
from .board_transformer import BoardTransformer
from .pieces_detector import PiecesDetector
from .square_mapper import SquareMapper
from .board_state import BoardState
from .fen_builder import FENBuilder

class ChessPipeline:
    def __init__(self, board_model, pieces_model):
        self.board_detector = BoardDetector(board_model)
        self.board_transformer = BoardTransformer()
        self.pieces_detector = PiecesDetector(pieces_model)
        self.board_state = BoardState()
        self.fen_builder = FENBuilder()

    def process(self, image, orientation):
        board = self.board_detector.detect(image)

        board_image = self.board_transformer.crop(
            image,
            board.bbox
        )

        pieces = self.pieces_detector.detect(board_image)

        mapper = SquareMapper(
            board_image.shape[1::-1],
            orientation
        )

        for piece in pieces:
            piece.square = mapper.get_square(piece.bbox)

        state = self.board_state.from_pieces(pieces)
        fen = self.fen_builder.build(state)

        return board, pieces, state, fen