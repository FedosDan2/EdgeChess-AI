from pathlib import Path
from ultralytics import YOLO

# ============================================================
# CONFIG
# ============================================================

BASE_WEIGHTS = "./CV_3D/weights/best_3d_detection.pt"
DATA_YAML = "./CV_3D/synthetic-demo-aug/data.yaml"
PROJECT = "./CV_3D/runs"
NAME = "3d_finetune_synthetic"

EPOCHS = 100
BATCH = 8
IMGSZ = 640
DEVICE = 0

# Fine-tuning: маленький LR, чтобы не сломать выученные признаки
LR0 = 0.001
LRF = 0.01
PATIENCE = 10
SEED = 42


# ============================================================
# CHECK: классы должны совпадать!
# ============================================================

def check_classes():
    """Сверяет nc и names между базовой моделью и новым датасетом."""
    import yaml
    with open(DATA_YAML, "r") as f:
        ds = yaml.safe_load(f)

    model = YOLO(BASE_WEIGHTS)
    model_nc = model.model.nc
    ds_nc = ds["nc"]

    print(f"📊 Базовая модель: nc={model_nc}")
    print(f"📊 Датасет:        nc={ds_nc}")

    if model_nc != ds_nc:
        raise ValueError(
            f"❌ НЕСОВПАДЕНИЕ классов! Модель={model_nc}, датасет={ds_nc}. "
            f"Fine-tuning невозможен — переобучи с нуля или исправь data.yaml."
        )

    # Сверяем имена
    model_names = list(model.names.values())
    ds_names = list(ds["names"].values()) if isinstance(ds["names"], dict) else ds["names"]
    if model_names != ds_names:
        print("⚠️  Порядок/имена классов отличаются:")
        print(f"   Модель:  {model_names}")
        print(f"   Датасет: {ds_names}")
        print("   Fine-tuning пройдёт, но метрики могут быть некорректны.")
    else:
        print("✅ Классы совпадают полностью.")


# ============================================================
# MAIN
# ============================================================

def main():
    if not Path(BASE_WEIGHTS).exists():
        raise FileNotFoundError(BASE_WEIGHTS)
    if not Path(DATA_YAML).exists():
        raise FileNotFoundError(DATA_YAML)

    check_classes()

    Path(PROJECT).mkdir(parents=True, exist_ok=True)

    # Загружаем ОБУЧЕННУЮ модель, а не базовую yolo11s.pt
    model = YOLO(BASE_WEIGHTS)

    results = model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        batch=BATCH,
        imgsz=IMGSZ,
        device=DEVICE,
        workers=4,
        cache="disk",
        project=PROJECT,
        name=NAME,
        seed=SEED,
        save=True,
        val=True,
        amp=True,
        verbose=True,

        # --- Fine-tuning параметры ---
        optimizer="AdamW",
        lr0=LR0,          # в 10 раз меньше обычного (0.01 -> 0.001)
        lrf=LRF,
        weight_decay=0.0005,
        warmup_epochs=2,

        # --- Аугментации: мягкие, чтобы не сбить признаки ---
        hsv_h=0.01, hsv_s=0.3, hsv_v=0.3,
        degrees=5.0,
        translate=0.05,
        scale=0.2,
        perspective=0.001,
        flipud=0.0,
        fliplr=0.0,       # шахматы нельзя зеркалить (углы перепутаются)
        mosaic=0.0,       # отключено — на дообучении мешает
        mixup=0.0,
        cutmix=0.0,

        # --- Loss ---
        box=7.5,
        cls=0.5,
        dfl=1.5,
    )

    best = Path(PROJECT) / NAME / "weights" / "best.pt"
    print("\n" + "=" * 60)
    print("✅ FINE-TUNING ЗАВЕРШЁН")
    print("=" * 60)
    print(f"Новые веса: {best}")
    print(f"Скопируй их в CV_3D/weights/best_3d_detection.pt для инференса.")


if __name__ == "__main__":
    main()