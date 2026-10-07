from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "board2d": ROOT / "CV_2D/weights/best_board_detect.pt",
    "pieces2d": ROOT / "CV_2D/weights/best_board_and_pieces.pt",
    "chess3d": ROOT / "CV_3D/weights/best_3d_detection.pt",
}
PROFILES = {"2d": ("board2d", "pieces2d"), "3d": ("chess3d",)}
BACKENDS = ("onnx", "rknn_fp16", "rknn_int8")
CORNER_NAMES = (
    "corner_black_right",
    "corner_black_left",
    "corner_white_right",
    "corner_white_left",
)


def piece_symbol(name):
    parts = name.replace("-", "_").split("_")
    if len(parts) != 2 or parts[0] not in ("w", "b", "white", "black"):
        return None
    symbol = {
        "pawn": "p",
        "rook": "r",
        "knight": "n",
        "bishop": "b",
        "queen": "q",
        "king": "k",
    }.get(parts[1])
    return symbol.upper() if symbol and parts[0] in ("w", "white") else symbol
