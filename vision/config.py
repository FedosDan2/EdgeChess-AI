from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "board2d": ROOT / "CV_2D/weights/best_board_detect.pt",
    "pieces2d": ROOT / "CV_2D/weights/best_board_and_pieces.pt",
    "chess3d": ROOT / "CV_3D/weights/best_3d_detection.pt",
    "chess3d_m": ROOT / "CV_3D/weights/best_new_scratch.pt",
}
MODELS_3D = {"chess3d_m": "YOLOv8m", "chess3d": "YOLO11s · дообученная"}
DEFAULT_3D_MODEL = "chess3d_m"
PROFILES = {"2d": ("board2d", "pieces2d"), "3d": (DEFAULT_3D_MODEL,)}
MODEL_DATA = {key: key for key in MODELS}
MODEL_DATA["chess3d_m"] = "synthetic3d"


def profile_models(profile, model=None):
    if profile not in PROFILES:
        raise ValueError("Unknown pipeline")
    if profile == "2d":
        return PROFILES[profile]
    key = model or DEFAULT_3D_MODEL
    if key not in MODELS_3D:
        raise ValueError("Unknown 3D model")
    return (key,)


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
