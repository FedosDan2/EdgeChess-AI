import cv2
import numpy as np
import pytest
from vision.geometry import board_geometry, placement
from vision.pipeline import Pipeline


def detection(name, box, score=0.9):
    return {"class_name": name, "xyxy": box, "confidence": score}


def test_2d_crop_coordinates_and_orientation(monkeypatch):
    import vision.pipeline as module

    calls = []

    class FakeModel:
        def __init__(self, key, *args):
            self.key = key

        def close(self):
            pass

        def predict(self, image, confidence):
            calls.append((self.key, image.shape))
            ds = (
                [detection("chessboard", [10, 20, 90, 100])]
                if self.key == "board2d"
                else [
                    detection("w-rook", [1, 71, 9, 79]),
                    detection("b-king", [71, 1, 79, 9]),
                ]
            )
            return ds, dict(preprocess_ms=1.0, inference_ms=2.0, postprocess_ms=1.0)

    monkeypatch.setattr(module, "Model", FakeModel)
    pipeline = Pipeline("2d")
    result = pipeline.predict(np.zeros((120, 120, 3), np.uint8))
    assert calls == [("board2d", (120, 120, 3)), ("pieces2d", (80, 80, 3))]
    assert result["placement"] == "7k/8/8/8/8/8/8/R7"
    assert result["pieces"][0]["xyxy"] == [11, 91, 19, 99]
    assert result["timings"]["inference_ms"] == 4
    rotated = pipeline.predict(np.zeros((120, 120, 3), np.uint8), "black")
    assert rotated["placement"] == "7R/8/8/8/8/8/8/k7"


def test_semantic_corners_use_black_players_perspective():
    detections = [
        detection("corner_" + name, [x - 1, y - 1, x + 1, y + 1])
        for name, (x, y) in {
            "white_left": (0, 80),
            "white_right": (80, 80),
            "black_left": (80, 0),
            "black_right": (0, 0),
        }.items()
    ]
    matrix, _, status = board_geometry(detections, "3d")
    assert status == "ok"
    # Bottom of the box is the base of a 3D piece, rather than its center.
    fen, pieces, warnings = placement(
        [detection("white_rook", [1, 66, 9, 76])], matrix, "3d"
    )
    assert pieces[0]["square"] == "a1"
    assert fen == "8/8/8/8/8/8/8/R7" and not warnings
    assert board_geometry(detections[:-1], "3d")[2] == "corners_missing"
    crossed = [dict(d) for d in detections]
    crossed[0]["xyxy"] = detections[2]["xyxy"]
    assert board_geometry(crossed, "3d")[2] == "corners_invalid"


def test_conflicts_outside_and_missing_board_are_explicit():
    matrix = np.eye(3)
    ds = [
        detection("w-king", [0, 0, 1, 1], 0.9),
        detection("b-queen", [0, 0, 1, 1], 0.8),
        detection("b-pawn", [-2, -2, -1, -1]),
    ]
    fen, _, warnings = placement(ds, matrix, "2d")
    assert fen == "K7/8/8/8/8/8/8/8"
    assert warnings == ["cell_conflict:a8", "piece_outside_board"]
    assert board_geometry([], "2d") == (None, [], "board_missing")
