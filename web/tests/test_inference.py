"""Exercise real CPU model when conversion artifacts are available."""
import cv2
import numpy as np
import pytest

from backend.inference import Detector, ROOT, preprocess_image


def test_landscape_letterbox_maps_back():
    from convert.common import postprocess
    original = np.zeros((720, 960, 3), dtype=np.uint8)
    original[:, :, 2] = 255
    _, rgb, tensor, info = preprocess_image(original)
    assert tensor.shape == (1, 3, 640, 640)
    assert rgb[80, 0].tolist() == [255, 0, 0]
    assert rgb[0, 0].tolist() == [114, 114, 114]
    prediction = np.array([[[320], [320], [640], [480], [.9]]], dtype=np.float32)
    detection = postprocess(prediction, info, ["piece"])[0]
    assert detection["xyxy"] == pytest.approx([0, 0, 960, 720])


@pytest.mark.skipif(not (ROOT / "convert/artifacts/chess3d_m/model.onnx").exists(), reason="Export model first")
def test_real_model_jpeg_and_invalid_image(monkeypatch):
    monkeypatch.setenv("EDGECHESS_PROFILE","3d")
    detector = Detector()
    ok, jpeg = cv2.imencode('.jpg', np.zeros((720, 960, 3), dtype=np.uint8))
    assert ok
    result = detector.predict(jpeg.tobytes())
    assert result["width"] == 960 and result["height"] == 720
    assert result["timings"]["processing_ms"] >= result["timings"]["inference_ms"] > 0
    with pytest.raises(Exception):
        detector.predict(b"invalid jpeg")
    detector.close()


@pytest.mark.skipif(not all((ROOT / f"convert/artifacts/{key}/model.onnx").exists()
    for key in ("chess3d_m", "chess3d", "board2d", "pieces2d")), reason="Export models first")
def test_switch_models_releases_sessions_and_keeps_2d(monkeypatch):
    monkeypatch.setenv("EDGECHESS_PROFILE", "3d")
    detector = Detector()
    try:
        assert detector.describe()["model"] == "chess3d_m"
        previous = detector.pipeline
        sessions = list(previous.models.values())
        detector.configure("3d", "onnx", "chess3d")
        assert detector.describe()["model"] == "chess3d"
        assert not previous.models and all(m.session is None for m in sessions)
        current = detector.pipeline
        detector.configure("3d", "onnx", "chess3d")
        assert detector.pipeline is current
        with pytest.raises(ValueError):
            detector.configure("3d", "onnx", "invalid")
        assert detector.pipeline is current
        detector.configure("2d", "onnx", "chess3d_m")
        assert set(detector.pipeline.models) == {"board2d", "pieces2d"}
        assert not current.models
        _, jpeg = cv2.imencode('.jpg', np.zeros((640, 640, 3), dtype=np.uint8))
        assert detector.predict(jpeg.tobytes())["profile"] == "2d"
        detector.configure("3d", "onnx", "chess3d_m")
        assert detector.predict(jpeg.tobytes())["model"] == "chess3d_m"
    finally:
        detector.close()
