"""Convert detections to cells; never infer pieces from the renderer's state."""

import math
import cv2
import numpy as np
from .config import CORNER_NAMES, piece_symbol


def board_geometry(detections, profile, orientation="white"):
    if orientation not in ("white", "black"):
        raise ValueError("orientation must be white or black")
    if profile == "2d":
        boards = [d for d in detections if d["class_name"] == "chessboard"]
        if not boards:
            return None, [], "board_missing"
        board = max(boards, key=lambda d: d["confidence"])
        x1, y1, x2, y2 = board["xyxy"]
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None, [], "board_invalid"
        src = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
        corners = [board]
    else:
        best = {}
        for d in detections:
            name = d["class_name"]
            if name in CORNER_NAMES and (
                name not in best or d["confidence"] > best[name]["confidence"]
            ):
                best[name] = d
        if len(best) != 4:
            return None, list(best.values()), "corners_missing"
        # Author annotations: black_right -> a8, black_left -> h8,
        # white_right -> h1, white_left -> a1; canonical view, white below.
        src = np.float32(
            [
                [
                    (best[n]["xyxy"][0] + best[n]["xyxy"][2]) / 2,
                    (best[n]["xyxy"][1] + best[n]["xyxy"][3]) / 2,
                ]
                for n in CORNER_NAMES
            ]
        )
        corners = [best[n] for n in CORNER_NAMES]
        if not cv2.isContourConvex(src) or abs(cv2.contourArea(src)) < 64:
            return None, corners, "corners_invalid"
    dst = np.float32([[0, 0], [8, 0], [8, 8], [0, 8]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        return None, corners, "board_invalid"
    if profile == "2d" and orientation == "black":
        matrix = np.array([[-1, 0, 8], [0, -1, 8], [0, 0, 1]], dtype=float) @ matrix
    return matrix, corners, "ok"


def placement(detections, matrix, profile):
    cells, warnings, pieces = {}, [], []
    for d in sorted(detections, key=lambda x: x["confidence"], reverse=True):
        symbol = piece_symbol(d["class_name"])
        if not symbol:
            continue
        x1, y1, x2, y2 = d["xyxy"]
        point = (
            (x1 + x2) / 2,
            (y1 + y2) / 2 + ((y2 - y1) * 0.4 if profile == "3d" else 0),
        )
        x, y = cv2.perspectiveTransform(np.float32([[point]]), matrix)[0, 0]
        if not np.isfinite([x, y]).all() or not (0 <= x < 8 and 0 <= y < 8):
            warnings.append("piece_outside_board")
            continue
        col, row = int(x), int(y)
        square = f"{'abcdefgh'[col]}{8 - row}"
        record = {**d, "square": square, "symbol": symbol}
        pieces.append(record)
        if (row, col) in cells:
            warnings.append("cell_conflict:" + square)
        else:
            cells[row, col] = symbol
    rows = []
    for row in range(8):
        value, empty = "", 0
        for col in range(8):
            symbol = cells.get((row, col))
            if symbol:
                value += (str(empty) if empty else "") + symbol
                empty = 0
            else:
                empty += 1
        rows.append(value + (str(empty) if empty else ""))
    return "/".join(rows), pieces, sorted(set(warnings))


def board_crop(image, board):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = board["xyxy"]
    x1, y1, x2, y2 = (
        max(0, math.floor(x1)),
        max(0, math.floor(y1)),
        min(w, math.ceil(x2)),
        min(h, math.ceil(y2)),
    )
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Board crop is outside the image")
    return image[y1:y2, x1:x2], (x1, y1)
