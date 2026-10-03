"""
Скрипт подготовки 2D шахматных датасетов для обучения двух моделей YOLO.
"""

import os
import shutil
import yaml
from pathlib import Path
from tqdm import tqdm

# ============================================================
# CONFIG - Пути относительно ЭТОГО скрипта
# ============================================================

# Получаем абсолютный путь к папке со скриптом
SCRIPT_DIR = Path(__file__).parent.resolve()

# Пути к РАСПАКОВАННЫМ датасетам
RAW_BOARD_DIR = SCRIPT_DIR / "CV_2D" / "data" / "dirty_data" / "board"
RAW_PIECES_DIR = SCRIPT_DIR / "CV_2D" / "data" / "dirty_data" / "board_and_pieces"

# Куда сохранять готовые датасеты
OUTPUT_BOARD_DIR = SCRIPT_DIR / "CV_2D" / "data" / "clean_data" / "board_dataset"
OUTPUT_PIECES_DIR = SCRIPT_DIR / "CV_2D" / "data" / "clean_data" / "pieces_dataset"

# ============================================================
# DIAGNOSTICS
# ============================================================

def check_paths():
    """Проверяет существование папок и выводит диагностику."""
    print("=" * 60)
    print(" Диагностика путей")
    print("=" * 60)
    print(f"📁 Скрипт запущен из: {SCRIPT_DIR}")
    print(f"📁 Ищем датасет доски в: {RAW_BOARD_DIR}")
    print(f"   Существует: {RAW_BOARD_DIR.exists()}")
    print(f"📁 Ищем датасет фигур в: {RAW_PIECES_DIR}")
    print(f"   Существует: {RAW_PIECES_DIR.exists()}")
    
    # Проверяем родительскую папку
    dirty_data_dir = SCRIPT_DIR / "CV_2D" / "data" / "dirty_data"
    if dirty_data_dir.exists():
        print(f"\n Содержимое dirty_data/:")
        for item in dirty_data_dir.iterdir():
            print(f"   - {item.name} {'(папка)' if item.is_dir() else '(файл)'}")
    else:
        print(f"\n Папка dirty_data не найдена: {dirty_data_dir}")
    
    print("=" * 60)
    print()

# ============================================================
# CLASS MAPPINGS
# ============================================================

PIECES_CLASSES = {
    0: "chessboard",
    1: "b-bishop",
    2: "b-king",
    3: "b-knight",
    4: "b-pawn",
    5: "b-queen",
    6: "b-rook",
    7: "w-bishop",
    8: "w-king",
    9: "w-knight",
    10: "w-pawn",
    11: "w-queen",
    12: "w-rook"
}

BOARD_CLASSES = {0: "chessboard"}

# ============================================================
# HELPERS
# ============================================================

def copy_and_rename_valid(src_dir: Path, dst_dir: Path):
    """Копирует данные, переименовывая папку 'valid' в 'val'."""
    splits = ["train", "valid", "test"]
    
    for split in splits:
        src_split_dir = src_dir / split
        if not src_split_dir.exists():
            continue
            
        dst_split_name = "val" if split == "valid" else split
        dst_images = dst_dir / "images" / dst_split_name
        dst_labels = dst_dir / "labels" / dst_split_name
        
        dst_images.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)
        
        src_images = src_split_dir / "images"
        if src_images.exists():
            for img in src_images.iterdir():
                shutil.copy2(img, dst_images / img.name)
                
        src_labels = src_split_dir / "labels"
        if src_labels.exists():
            for lbl in src_labels.iterdir():
                shutil.copy2(lbl, dst_labels / lbl.name)

# ============================================================
# PROCESS BOARD DATASET
# ============================================================

def prepare_board_dataset():
    print("=" * 60)
    print("1. Подготовка датасета для детекции ДОСКИ")
    print("=" * 60)
    
    if not RAW_BOARD_DIR.exists():
        print(f"❌ Папка не найдена: {RAW_BOARD_DIR}")
        print("\n💡 Возможные решения:")
        print("   1. Распакуйте датасет в эту папку")
        print("   2. Или измените RAW_BOARD_DIR в скрипте")
        print(f"\n📂 Текущее содержимое CV_2D/data/:")
        data_dir = SCRIPT_DIR / "CV_2D" / "data"
        if data_dir.exists():
            for item in data_dir.rglob("*"):
                if item.is_dir():
                    print(f"   {item.relative_to(data_dir)}")
        return False

    OUTPUT_BOARD_DIR.mkdir(parents=True, exist_ok=True)
    copy_and_rename_valid(RAW_BOARD_DIR, OUTPUT_BOARD_DIR)
    
    yaml_data = {
        "path": str(OUTPUT_BOARD_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": 1,
        "names": BOARD_CLASSES
    }
    
    yaml_path = OUTPUT_BOARD_DIR / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_data, f, sort_keys=False, allow_unicode=True)
        
    print(f"✅ Готово! Датасет сохранен в: {OUTPUT_BOARD_DIR}")
    print(f"   Классов: {yaml_data['nc']} ({BOARD_CLASSES})")
    return True

# ============================================================
# PROCESS PIECES DATASET
# ============================================================

def prepare_pieces_dataset():
    print("\n" + "=" * 60)
    print("2. Подготовка датасета для детекции ФИГУР (сдвиг классов)")
    print("=" * 60)
    
    if not RAW_PIECES_DIR.exists():
        print(f"❌ Папка не найдена: {RAW_PIECES_DIR}")
        print("\n💡 Возможные решения:")
        print("   1. Распакуйте датасет в эту папку")
        print("   2. Или измените RAW_PIECES_DIR в скрипте")
        return False

    OUTPUT_PIECES_DIR.mkdir(parents=True, exist_ok=True)
    
    splits = ["train", "valid", "test"]
    for split in splits:
        src_split_dir = RAW_PIECES_DIR / split
        if not src_split_dir.exists():
            continue
            
        dst_split_name = "val" if split == "valid" else split
        dst_images = OUTPUT_PIECES_DIR / "images" / dst_split_name
        dst_labels = OUTPUT_PIECES_DIR / "labels" / dst_split_name
        
        dst_images.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)
        
        src_images = src_split_dir / "images"
        if src_images.exists():
            for img in src_images.iterdir():
                shutil.copy2(img, dst_images / img.name)
                
        src_labels = src_split_dir / "labels"
        if src_labels.exists():
            for lbl in tqdm(src_labels.iterdir(), desc=f"Обработка {dst_split_name}"):
                with open(lbl, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = []
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) != 5:
                        continue
                    
                    old_class_id = int(parts[0])
                    new_class_id = old_class_id + 1
                    
                    if new_class_id <= 12:
                        new_line = f"{new_class_id} {parts[1]} {parts[2]} {parts[3]} {parts[4]}\n"
                        new_lines.append(new_line)
                
                with open(dst_labels / lbl.name, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

    yaml_data = {
        "path": str(OUTPUT_PIECES_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": 13,
        "names": PIECES_CLASSES
    }
    
    yaml_path = OUTPUT_PIECES_DIR / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_data, f, sort_keys=False, allow_unicode=True)
        
    print(f"✅ Готово! Датасет сохранен в: {OUTPUT_PIECES_DIR}")
    print(f"   Классов: {yaml_data['nc']} (0: chessboard, 1-12: фигуры)")
    return True

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n🚀 Запуск подготовки 2D шахматных датасетов...\n")
    
    # Сначала диагностика
    check_paths()
    
    board_success = prepare_board_dataset()
    pieces_success = prepare_pieces_dataset()
    
    if board_success and pieces_success:
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ДАТАСЕТЫ УСПЕШНО ПОДГОТОВЛЕНЫ!")
        print("=" * 60)
        print("\n📌 Команда для обучения модели ДОСКИ:")
        print(f"yolo task=detect mode=train data={OUTPUT_BOARD_DIR}/data.yaml model=yolov8n.pt epochs=50 imgsz=640 batch=8")
        
        print("\n📌 Команда для обучения модели ФИГУР:")
        print(f"yolo task=detect mode=train data={OUTPUT_PIECES_DIR}/data.yaml model=yolov8n.pt epochs=50 imgsz=640 batch=8")
    else:
        print("\n" + "=" * 60)
        print("⚠️  Подготовка завершена с ошибками")
        print("=" * 60)
        print("Про пути выше и убедитесь, что датасеты распакованы.")

if __name__ == "__main__":
    main()