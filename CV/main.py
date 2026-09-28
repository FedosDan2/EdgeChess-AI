from pathlib import Path
import cv2

from pipeline.pipeline import ChessPipeline

WEIGHTS = Path(
    "/home/fedosdan2/Study/EdgeChess-AI/CV/pipeline/weights"
)

pipeline = ChessPipeline(
    board_model=WEIGHTS / "best_board_detect.pt",
    pieces_model=WEIGHTS / "best_board_and_pieces.pt",
)

image = cv2.imread(
    "/home/fedosdan2/Study/EdgeChess-AI/CV/image.png"
)

orientation = 1  # 1 = белые снизу, 0 = чёрные снизу

board, pieces, state, fen = pipeline.process(
    image,
    orientation=1
)

for piece in pieces:
    print(piece.name, "->", piece.square)

print("\nBOARD:")
print(state)

print("\nFEN:")
print(fen)