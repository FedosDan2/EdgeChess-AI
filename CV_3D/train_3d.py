"""
Обучение YOLOv11s с нуля на synthetic-demo-aug (16 классов: 12 фигур + 4 угла).
Стартуем с yolo11s.pt (COCO), а НЕ с best_3d_detection.pt.
"""
from pathlib import Path
import yaml
from ultralytics import YOLO

# ============================================================
# CONFIG
# ============================================================
DATA_YAML = "./CV_3D/synthetic-demo-aug/data.yaml"   # аугментированный train
# DATA_YAML = "./CV_3D/synthetic-demo/data.yaml"     # оригинальный (меньше данных)

MODEL = "yolov8n.pt"          # базовая предобучка, старт с нуля
PROJECT = "./CV_3D/runs"
NAME = "3d_from_scratch"

EPOCHS = 100
BATCH = 8
IMGSZ = 640
DEVICE = 0
SEED = 42

# Ожидаемые имена углов (классы 12-15) — downstream пайплайн завязан на них
EXPECTED_CORNERS = ["corner_white_left", "corner_white_right",
                    "corner_black_left", "corner_black_right"]


def check_yaml():
    with open(DATA_YAML, "r", encoding="utf-8") as f:
        ds = yaml.safe_load(f)
    names = ds["names"]
    names = list(names.values()) if isinstance(names, dict) else names
    assert ds["nc"] == 16, f"Ожидался nc=16, получил {ds['nc']}"
    got = names[12:16]
    assert got == EXPECTED_CORNERS, (
        f"Порядок углов сломан!\n  ожидал: {EXPECTED_CORNERS}\n  получил: {got}\n"
        f"  board_detector.py ищет классы 12-15 в этом порядке."
    )
    print(f"✅ data.yaml валиден: nc=16, углы на местах {got}")


def main():
    check_yaml()
    Path(PROJECT).mkdir(parents=True, exist_ok=True)

    model = YOLO(MODEL)   # старт с COCO-предобучки, не с нашей веса

    results = model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        batch=BATCH,
        imgsz=IMGSZ,
        device=DEVICE,
        workers=8,
        cache="disk",
        project=PROJECT,
        name=NAME,
        seed=SEED,
        save=True, plots=True, val=True, amp=True, verbose=True,

        # --- с нуля: обычный LR, учим ВСЁ (без freeze) ---
        optimizer="AdamW",
        lr0=0.01,            # fine-tune было 0.001
        lrf=0.01,
        weight_decay=0.0005,
        warmup_epochs=3,

        # --- аугментации: сильнее, чем при дообучении ---
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        perspective=0.0005,  # микро-перспектива, не путает left/right
        flipud=0.0,
        fliplr=0.0,          # ← ЖЁСТКО 0: зеркало меняет left/right углы
        mosaic=0.8,          # при дообучении было 0.0
        mixup=0.1,
        cutmix=0.0,
        close_mosaic=15,     # последние 15 эпох — без mosaic (целые кадры)

        # --- loss ---
        box=7.5, cls=0.5, dfl=1.5,
    )

    best = Path(PROJECT) / NAME / "weights" / "best.pt"
    print("\n" + "=" * 60)
    print("✅ ОБУЧЕНИЕ С НУЛЯ ЗАВЕРШЕНО")
    print("=" * 60)
    print(f"Веса: {best}")
    print(f"Сравни с базой: python eval_compare.py  (или ячейка 4 из теста)")


if __name__ == "__main__":
    main()