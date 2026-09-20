"""Create lossless, already-letterboxed calibration images on the Windows PC.

RKNN calibration must see the same geometry/colors as runtime inference.
The list uses paths relative to its own directory (data), as required by Toolkit2.
"""
import cv2
from common import ROOT, images, preprocess, save_json, sha256


def main():
    output = ROOT / "data/calibration"
    output.mkdir(parents=True, exist_ok=True)
    paths, records = [], []
    # Decode-pixel hashes also catch identical images with different encodings.
    import hashlib
    test_hashes = {hashlib.sha256(preprocess(p)[1].tobytes()).hexdigest() for p in images("test")}
    for source in images("train"):
        _, rgb, _, _ = preprocess(source)
        pixel_hash = hashlib.sha256(rgb.tobytes()).hexdigest()
        if pixel_hash in test_hashes:
            raise ValueError(f"Calibration image duplicates test pixels: {source}")
        path = output / (source.stem + ".png")
        success, encoded = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if not success:
            raise ValueError(f"Cannot encode {source}")
        encoded.tofile(path)
        paths.append(path.relative_to(ROOT).as_posix())
        records.append({"source": source.relative_to(ROOT).as_posix(), "source_sha256": sha256(source),
                        "prepared": paths[-1], "sha256": sha256(path), "pixel_sha256": pixel_hash})
    if not paths:
        raise ValueError("Calibration subset is empty")
    relative_paths = [path.removeprefix("data/") for path in paths]
    (ROOT / "data/calibration.txt").write_text("\n".join(relative_paths) + "\n", encoding="utf-8")
    save_json(ROOT / "data/calibration_manifest.json", {"imgsz": 640, "pad": 114, "images": records})
    print(f"Prepared {len(paths)} PNG files; calibration.txt contains relative paths")


if __name__ == "__main__":
    main()
