"""
ChessRender360 Dataset Setup Script
====================================
Автоматически скачивает датасет с Kaggle и подготавливает его для обучения YOLO.

Требования:
    pip install kagglehub albumentations opencv-python pyyaml tqdm
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
import yaml
from tqdm import tqdm


# ============================================================
# CONFIG
# ============================================================

# Kaggle dataset slug (owner/dataset-name)
KAGGLE_DATASET = "mmkoya/chessrender360"

# Куда сохранять готовый YOLO-датасет
OUTPUT_PATH = Path("./EdgeChess-AI/CV_3D/dataset")

# Параметры обработки
IMAGE_SIZE = 1024
CORNER_BOX_SIZE = 100

TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
SEED = 42

AUGMENTATIONS_PER_IMAGE = 2  # Сколько аугментированных копий на train


# ============================================================
# CLASSES
# ============================================================

PIECE_CLASSES = [
    "white_queen", "white_king", "white_bishop", "white_knight",
    "white_rook", "white_pawn",
    "black_queen", "black_king", "black_bishop", "black_knight",
    "black_rook", "black_pawn",
]

CORNER_CLASSES = [
    "corner_white_left", "corner_white_right",
    "corner_black_left", "corner_black_right",
]

CLASS_NAMES = PIECE_CLASSES + CORNER_CLASSES

CLASS_TO_ID = {name: i for i, name in enumerate(CLASS_NAMES)}


# ============================================================
# STEP 1: DOWNLOAD
# ============================================================

def check_kagglehub_installed():
    """Проверяет, установлен ли kagglehub."""
    try:
        import kagglehub
        return True
    except ImportError:
        return False


def install_kagglehub():
    """Устанавливает kagglehub."""
    print("📦 Установка kagglehub...")
    subprocess.run([sys.executable, "-m", "pip", "install", "kagglehub"], check=True)


def download_dataset() -> Path:
    """
    Скачивает датасет с Kaggle через kagglehub.
    Возвращает путь к распакованному датасету.
    """
    import kagglehub
    
    print(f"️  Скачивание датасета {KAGGLE_DATASET}...")
    print(f"   Это может занять время (~26 GB)")
    print(f"   Требуется авторизация Kaggle (автоматически)")
    
    try:
        path = kagglehub.dataset_download(KAGGLE_DATASET)
        print(f"✅ Скачивание завершено!")
        print(f"   Путь: {path}")
        return Path(path)
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        print("\n🔧 Возможные причины:")
        print("   1. Не установлен kagglehub -> pip install kagglehub")
        print("   2. Не выполнена авторизация Kaggle")
        print("   3. Нет доступа к датасету (нужно принять правила на Kaggle)")
        print("\n Для авторизации выполните:")
        print("   kagglehub login")
        sys.exit(1)


def find_dataset_root(download_dir: Path) -> Path:
    """
    Находит корневую папку датасета.
    Ищем папку с annotations/ и rgb/.
    """
    # Проверяем саму папку
    if (download_dir / "annotations").exists() and (download_dir / "rgb").exists():
        return download_dir
    
    # Ищем в подпапках
    for item in download_dir.iterdir():
        if item.is_dir():
            if (item / "annotations").exists() and (item / "rgb").exists():
                return item
            # Рекурсивно
            sub = find_dataset_root(item)
            if sub:
                return sub
    
    return None


# ============================================================
# STEP 2: AUGMENTATIONS
# ============================================================

def create_augmentation(image_size: int):
    """Создаёт пайплайн аугментаций."""
    return A.Compose(
        [
            A.LongestMaxSize(max_size=image_size, p=1.0),
            A.PadIfNeeded(min_height=image_size, min_width=image_size,
                          border_mode=cv2.BORDER_CONSTANT, fill=0, p=1.0),

            A.ShiftScaleRotate(shift_limit=0.03, scale_limit=0.08, rotate_limit=5,
                               border_mode=cv2.BORDER_CONSTANT, fill=0, p=0.30),
            A.Perspective(scale=(0.02, 0.06), keep_size=True, p=0.15),

            A.RandomBrightnessContrast(brightness_limit=0.20, contrast_limit=0.20, p=0.50),
            A.HueSaturationValue(hue_shift_limit=8, sat_shift_limit=15, val_shift_limit=12, p=0.35),
            A.RandomGamma(gamma_limit=(80, 120), p=0.25),
            A.RGBShift(r_shift_limit=10, g_shift_limit=10, b_shift_limit=10, p=0.20),

            A.OneOf([
                A.GaussianBlur(blur_limit=(3, 5)),
                A.MotionBlur(blur_limit=(3, 5)),
                A.GaussNoise(std_range=(0.01, 0.04)),
            ], p=0.25),

            A.ImageCompression(quality_range=(70, 98), p=0.35),
            A.Sharpen(alpha=(0.1, 0.3), lightness=(0.8, 1.2), p=0.15),
        ],
        bbox_params=A.BboxParams(
            format="pascal_voc",
            label_fields=["class_labels"],
            min_area=4,
            min_visibility=0.20,
            clip=True,
        ),
    )


# ============================================================
# STEP 3: PROCESSING
# ============================================================

def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def save_image(path: Path, image: np.ndarray, jpeg_quality: int = 95):
    path.parent.mkdir(parents=True, exist_ok=True)
    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), image_bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])


def corner_to_bbox(point, box_size: int, image_width: int, image_height: int):
    x, y = point
    half = box_size / 2.0
    x1 = max(0, min(x - half, image_width - 1))
    y1 = max(0, min(y - half, image_height - 1))
    x2 = max(0, min(x + half, image_width - 1))
    y2 = max(0, min(y + half, image_height - 1))
    return [x1, y1, x2, y2]


def parse_annotation(annotation: dict, image_width: int, image_height: int, corner_box_size: int):
    """Парсит аннотацию и возвращает bbox'ы и class_ids."""
    bboxes = []
    class_ids = []

    # Pieces
    for piece in annotation.get("pieces", []):
        piece_name = piece["piece_name"]
        if piece_name not in CLASS_TO_ID:
            continue
        bbox = piece["bbox"]
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            continue
        bboxes.append([float(x1), float(y1), float(x2), float(y2)])
        class_ids.append(CLASS_TO_ID[piece_name])

    # Corners
    corners = annotation.get("board_corners", {})
    corner_order = ["white_left", "white_right", "black_left", "black_right"]

    for corner_name, class_name in zip(corner_order, CORNER_CLASSES):
        if corner_name not in corners:
            continue
        point = corners[corner_name]
        if len(point) != 2:
            continue
        bbox = corner_to_bbox(point, box_size=corner_box_size,
                              image_width=image_width, image_height=image_height)
        bboxes.append(bbox)
        class_ids.append(CLASS_TO_ID[class_name])

    return bboxes, class_ids


def bbox_to_yolo(bbox, image_width, image_height):
    x1, y1, x2, y2 = bbox
    x1 = np.clip(x1, 0, image_width)
    x2 = np.clip(x2, 0, image_width)
    y1 = np.clip(y1, 0, image_height)
    y2 = np.clip(y2, 0, image_height)
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        return None
    x_center = (x1 + x2) / 2.0
    y_center = (y1 + y2) / 2.0
    return (x_center / image_width, y_center / image_height,
            width / image_width, height / image_height)


def write_yolo_label(path: Path, bboxes, class_ids, image_width, image_height):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for bbox, class_id in zip(bboxes, class_ids):
            yolo_bbox = bbox_to_yolo(bbox, image_width, image_height)
            if yolo_bbox is None:
                continue
            x, y, w, h = yolo_bbox
            f.write(f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")


def find_image_path(annotation: dict, dataset_root: Path) -> Path | None:
    """
    Находит путь к изображению, пробуя несколько вариантов.
    Возвращает None, если изображение не найдено.
    """
    rgb_relative = annotation.get("rgb_path", "")
    if not rgb_relative:
        return None

    # Вариант 1: как есть в аннотации
    path = dataset_root / rgb_relative
    if path.exists():
        return path

    # Вариант 2: только имя файла (если в аннотации лишний префикс)
    filename = Path(rgb_relative).name
    path = dataset_root / "rgb" / filename
    if path.exists():
        return path

    # Вариант 3: ищем в подпапке rgb
    for rgb_dir in dataset_root.rglob("rgb"):
        path = rgb_dir / filename
        if path.exists():
            return path

    return None


def process_image(annotation_path: Path, dataset_root: Path, output_root: Path,
                  split: str, augmentation, output_name: str, corner_box_size: int):
    """Обрабатывает одно изображение."""
    with open(annotation_path, "r", encoding="utf-8") as f:
        annotation = json.load(f)

    rgb_path = find_image_path(annotation, dataset_root)
    if rgb_path is None:
        print(f"WARNING: image not found for {annotation_path}")
        return

    image = read_image(rgb_path)
    image_height, image_width = image.shape[:2]

    bboxes, class_ids = parse_annotation(annotation, image_width, image_height, corner_box_size)

    if len(bboxes) == 0:
        print(f"WARNING: no objects in {annotation_path}")
        return

    result = augmentation(image=image, bboxes=bboxes, class_labels=class_ids)
    image_aug = result["image"]
    bboxes_aug = result["bboxes"]
    class_ids_aug = result["class_labels"]

    image_output = output_root / "images" / split / f"{output_name}.jpg"
    save_image(image_output, image_aug)

    label_output = output_root / "labels" / split / f"{output_name}.txt"
    h, w = image_aug.shape[:2]
    write_yolo_label(label_output, bboxes_aug, class_ids_aug, w, h)


def split_annotations(annotations, train_ratio, val_ratio, test_ratio, seed):
    annotations = list(annotations)
    random.Random(seed).shuffle(annotations)
    n = len(annotations)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)
    return annotations[:train_end], annotations[train_end:val_end], annotations[val_end:]


def create_data_yaml(output_root: Path):
    data = {
        "path": str(output_root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(CLASS_NAMES),
        "names": {i: name for i, name in enumerate(CLASS_NAMES)},
    }
    yaml_path = output_root / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("ChessRender360 Dataset Setup")
    print("=" * 70)

    # --------------------------------------------------------
    # Шаг 1: Проверка kagglehub
    # --------------------------------------------------------
    print("\n[1/4] Проверка kagglehub...")
    if not check_kagglehub_installed():
        print("kagglehub не найден. Устанавливаю...")
        install_kagglehub()
    
    # --------------------------------------------------------
    # Шаг 2: Скачивание датасета
    # --------------------------------------------------------
    print("\n[2/4] Скачивание датасета...")
    dataset_root = download_dataset()

    # --------------------------------------------------------
    # Шаг 3: Поиск корневой папки
    # --------------------------------------------------------
    print("\n[3/4] Поиск структуры датасета...")
    actual_root = find_dataset_root(dataset_root)
    if actual_root is None:
        print(f"❌ Не удалось найти папку с annotations/ и rgb/ в {dataset_root}")
        sys.exit(1)
    
    print(f"✅ Найдено: {actual_root}")

    annotations_dir = actual_root / "annotations"
    annotation_files = sorted(annotations_dir.glob("*.json"))
    
    if not annotation_files:
        print(f"❌ JSON аннотации не найдены в {annotations_dir}")
        sys.exit(1)

    print(f"📊 Найдено {len(annotation_files)} аннотаций")

    # --------------------------------------------------------
    # Шаг 4: Обработка
    # --------------------------------------------------------
    print("\n[4/4] Обработка датасета...")
    output_root = OUTPUT_PATH.resolve()

    # Split
    train_files, val_files, test_files = split_annotations(
        annotation_files, TRAIN_RATIO, VAL_RATIO, TEST_RATIO, SEED
    )
    splits = {"train": train_files, "val": val_files, "test": test_files}

    print(f"\nDataset split:")
    print(f"  train: {len(train_files)}")
    print(f"  val:   {len(val_files)}")
    print(f"  test:  {len(test_files)}\n")

    # Create directories
    for split in ["train", "val", "test"]:
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Augmentation
    augmentation = create_augmentation(image_size=IMAGE_SIZE)

    # Process
    for split, files in splits.items():
        print(f"\nProcessing {split}: {len(files)} images")

        for annotation_path in tqdm(files, desc=split):
            base_name = annotation_path.stem.replace("annotation_", "rgb_")

            if split == "train":
                num_versions = AUGMENTATIONS_PER_IMAGE + 1
            else:
                num_versions = 1

            for version in range(num_versions):
                suffix = "original" if version == 0 else f"aug_{version - 1:03d}"
                output_name = f"{base_name}_{suffix}"

                try:
                    process_image(
                        annotation_path=annotation_path,
                        dataset_root=actual_root,
                        output_root=output_root,
                        split=split,
                        augmentation=augmentation,
                        output_name=output_name,
                        corner_box_size=CORNER_BOX_SIZE,
                    )
                except Exception as e:
                    print(f"\nERROR processing {annotation_path}: {e}")

    # YAML
    create_data_yaml(output_root)

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------
    print("\n" + "=" * 70)
    print("DONE!")
    print("=" * 70)
    print(f"\n📁 Датасет: {output_root}")
    print(f"📄 YAML:    {output_root / 'data.yaml'}")
    print(f"\n📋 Классы ({len(CLASS_NAMES)}):")
    for i, name in enumerate(CLASS_NAMES):
        print(f"  {i:2d}: {name}")
    
    print("\n✅ Готово к обучению YOLO!")
    print(f"   yolo task=detect mode=train data={output_root / 'data.yaml'} ...")


if __name__ == "__main__":
    main()