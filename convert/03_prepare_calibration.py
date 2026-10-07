"""Create lossless, already-letterboxed calibration images.

RKNN calibration must see the same geometry/colors as runtime inference.
The list uses paths relative to its own directory (data), as required by Toolkit2.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.inference import Model
from vision.geometry import board_geometry, board_crop
import cv2
from common import ROOT, images, preprocess, preprocess_image, save_json, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", choices=("board2d", "pieces2d", "chess3d"), required=True
    )
    args = parser.parse_args()
    directory = ROOT / "data" / args.model
    output = directory / "calibration"
    output.mkdir(parents=True, exist_ok=True)
    paths, records, skipped = [], [], []
    board_model = (
        Model("board2d", ROOT / "artifacts") if args.model == "pieces2d" else None
    )
    # Decode-pixel hashes also catch identical images with different encodings.
    import hashlib

    test_hashes = {
        hashlib.sha256(preprocess(p)[1].tobytes()).hexdigest()
        for p in images("test", args.model)
    }
    if board_model is not None:
        for source in images("test", args.model):
            original, _, _, _ = preprocess(source)
            detections, _ = board_model.predict(original)
            matrix, boards, _ = board_geometry(detections, "2d")
            if matrix is not None:
                crop, _ = board_crop(original, boards[0])
                test_hashes.add(
                    hashlib.sha256(preprocess_image(crop)[1].tobytes()).hexdigest()
                )
    for source in images("train", args.model):
        original, rgb, _, _ = preprocess(source)
        if hashlib.sha256(rgb.tobytes()).hexdigest() in test_hashes:
            raise ValueError(f"Calibration source duplicates test pixels: {source}")
        if board_model is not None:
            detections, _ = board_model.predict(original)
            matrix, boards, status = board_geometry(detections, "2d")
            if matrix is None:
                skipped.append({"source": str(source), "reason": status})
                continue
            crop, _ = board_crop(original, boards[0])
            _, rgb, _, _ = preprocess_image(crop)
        pixel_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
        if pixel_hash in test_hashes:
            raise ValueError(f"Calibration image duplicates test pixels: {source}")
        path = output / (source.stem + ".png")
        if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise ValueError(f"Cannot encode {source}")
        paths.append(path.relative_to(ROOT).as_posix())
        records.append(
            {
                "source": source.relative_to(ROOT).as_posix(),
                "source_sha256": sha256(source),
                "prepared": paths[-1],
                "sha256": sha256(path),
                "pixel_sha256": pixel_hash,
            }
        )
    if board_model is not None:
        board_model.close()
    if not paths:
        raise ValueError("Calibration subset is empty")
    relative_paths = [str((ROOT / path).relative_to(directory)) for path in paths]
    (directory / "calibration.txt").write_text(
        "\n".join(relative_paths) + "\n", encoding="utf-8"
    )
    save_json(
        directory / "calibration_manifest.json",
        {
            "imgsz": 640,
            "pad": 114,
            "images": records,
            "skipped": skipped,
            "board_crop": args.model == "pieces2d",
            "crop_model_sha256": board_model.digest if board_model else None,
        },
    )
    print(f"Prepared {len(paths)} PNG files; calibration.txt contains relative paths")


if __name__ == "__main__":
    main()
