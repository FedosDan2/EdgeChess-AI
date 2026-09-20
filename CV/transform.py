import cv2
import os
import numpy as np
from pathlib import Path


OUTPUT_ROOT = "/home/fedosdan2/Study/EdgeChess-AI/CV/yolo_chess_dataset"
IMAGE_TRAIN = f"{OUTPUT_ROOT}/images/train"
LABEL_TRAIN = f"{OUTPUT_ROOT}/labels/train"

# ID -> имя класса (числовые ключи!)
CLASS_NAMES = {
    0: "white_pawn",
    1: "white_rook",
    2: "white_knight",
    3: "white_bishop",
    4: "white_queen",
    5: "white_king",
    6: "black_pawn",
    7: "black_rook",
    8: "black_knight",
    9: "black_bishop",
    10: "black_queen",
    11: "black_king",
    12: "chessboard",
    13: "corner_white_left",
    14: "corner_white_right",
    15: "corner_black_left",
    16: "corner_black_right"
}

COLORS = {
    0: (0, 200, 0),     # white_pawn - зелёный
    1: (0, 150, 0),     # white_rook
    2: (0, 255, 100),   # white_knight
    3: (100, 255, 100), # white_bishop
    4: (200, 255, 200), # white_queen
    5: (255, 255, 255), # white_king
    6: (0, 0, 200),     # black_pawn - синий
    7: (0, 0, 150),     # black_rook
    8: (100, 100, 255), # black_knight
    9: (100, 100, 200), # black_bishop
    10: (200, 200, 255),# black_queen
    11: (0, 0, 255),    # black_king
    12: (255, 255, 255),# chessboard - белый
    13: (255, 255, 0),  # corner_white_left - жёлтый
    14: (255, 128, 0),  # corner_white_right - оранжевый
    15: (128, 0, 255),  # corner_black_left - фиолетовый
    16: (0, 255, 128)   # corner_black_right - бирюзовый
}


def draw_yolo_bbox(image, label_file):
    """Читает YOLO .txt файл и рисует bounding box'ы на изображении."""
    img_height, img_width = image.shape[:2]
    corners = {}

    if not os.path.exists(label_file):
        print(f"⚠️ Файл разметки не найден: {label_file}")
        return image, None

    with open(label_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

        for line in lines:
            parts = line.strip().split()
            if len(parts) != 5:
                continue

            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])

            x_center_px = x_center * img_width
            y_center_px = y_center * img_height
            w_px = width * img_width
            h_px = height * img_height

            x_min = int(x_center_px - w_px / 2)
            y_min = int(y_center_px - h_px / 2)
            x_max = int(x_center_px + w_px / 2)
            y_max = int(y_center_px + h_px / 2)

            x_min = max(0, x_min)
            y_min = max(0, y_min)
            x_max = min(img_width, x_max)
            y_max = min(img_height, y_max)

            # Сохраняем координаты углов (ID 13-16)
            if class_id in [13, 14, 15, 16]:
                corners[class_id] = (int(x_center_px), int(y_center_px))
                
                cx = int(x_center_px)
                cy = int(y_center_px)
                color = COLORS.get(class_id, (128, 128, 128))
                cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, 20, 2)

            # chessboard = 12
            thickness = 3 if class_id == 12 else 2
            color = COLORS.get(class_id, (128, 128, 128))
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max), color, thickness)

            label = CLASS_NAMES.get(class_id, f"class_{class_id}")
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
            )
            cv2.rectangle(image, (x_min, y_min - text_height - baseline), (x_min + text_width, y_min), color, -1)
            cv2.putText(image, label, (x_min, y_min - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0) if class_id == 12 else (255, 255, 255), 1)

    return image, corners


def get_ordered_corners_with_orientation(corners_dict, img_width, img_height):
    """
    Упрощённая версия: всегда разворачивает доску белыми вниз.
    """
    white_left = np.array(corners_dict[13])
    white_right = np.array(corners_dict[14])
    black_left = np.array(corners_dict[15])
    black_right = np.array(corners_dict[16])
    
    ordered = [black_right, black_left, white_left, white_right]
    white_at_bottom = 1
    
    return ordered, white_at_bottom


def apply_perspective_transform(image, corners, output_size=900, padding=50):
    """
    Применяет Perspective Transform по 4 углам доски с правильной ориентацией.
    """
    src_points = np.float32(corners)
    
    total_size = output_size + 2 * padding
    
    dst_points = np.float32([
        [output_size + padding, padding],
        [padding, padding],                      # top_left = a8
        [output_size + padding, output_size + padding],  # bottom_right = h1
        [padding, output_size + padding]         # bottom_left = a1
    ])
  
    M = cv2.getPerspectiveTransform(src_points, dst_points)
    warped = cv2.warpPerspective(image, M, (total_size, total_size))
    
    return warped, M


def draw_8x8_grid(image, output_size=900, padding=50, color=(0, 255, 255), thickness=1, white_at_bottom=True):
    """
    Рисует сетку 8x8 на изображении с учетом ориентации.
    """
    h, w = image.shape[:2]
    cell_size = output_size / 8
    
    # Вертикальные линии
    for i in range(1, 8):
        x = int(padding + i * cell_size)
        cv2.line(image, (x, padding), (x, padding + output_size), color, thickness)
    
    # Горизонтальные линии
    for i in range(1, 8):
        y = int(padding + i * cell_size)
        cv2.line(image, (padding, y), (padding + output_size, y), color, thickness)
    
    # Подписи колонок (a-h) и рядов (1-8)
    cols = "abcdefgh"
    for i in range(8):
        if white_at_bottom:
            # Буквы колонок снизу (ряд 1)
            cv2.putText(
                image, cols[i],
                (int(padding + i * cell_size + cell_size / 2 - 5), padding + output_size + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
            # Цифры рядов слева (1-8 снизу вверх)
            cv2.putText(
                image, str(i + 1),
                (padding - 25, int(padding + (7 - i) * cell_size + cell_size / 2 + 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
        else:
            # Перевернутая ориентация: буквы сверху, ряды 8-1 сверху вниз
            cv2.putText(
                image, cols[len(cols) - i - 1],
                (int(padding + i * cell_size + cell_size / 2 - 5), padding - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
            cv2.putText(
                image, str(i+1),
                (padding - 25, int(padding + i * cell_size + cell_size / 2 + 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
    
    return image


num = 0
# ==========================================
# ЗАПУСК
# ==========================================
img_files = [f for f in os.listdir(IMAGE_TRAIN) if f.endswith(('.jpg', '.jpeg', '.png'))]

if not img_files:
    print(" Изображения в папке train не найдены! Проверь пути.")
else:
    img_name_no_ext = Path(f"{IMAGE_TRAIN}/rgb_{num}.jpeg").stem
    label_path = f"{LABEL_TRAIN}/rgb_{num}.txt"
     
    selected_img = Path(f"{IMAGE_TRAIN}/rgb_{num}.jpeg")
    img_path = f"{IMAGE_TRAIN}/rgb_{num}.jpeg"

    print(f"🖼️  Визуализация изображения: {selected_img}")
    print(f"📄  Файл разметки: {img_name_no_ext}.txt")

    img = cv2.imread(img_path)
    if img is None:
        print("❌ Не удалось прочитать изображение. Проверь путь.")
    else:
        img_height, img_width = img.shape[:2]

        img_annotated, corners = draw_yolo_bbox(img.copy(), label_path)

        required_corners = {13, 14, 15, 16}
        found_corners = set(corners.keys())
        missing_corners = required_corners - found_corners

        if missing_corners:
            print(f"⚠️ Не найдены углы: {[CLASS_NAMES[c] for c in missing_corners]}")
            output_path = f"visualized_{selected_img}"
            cv2.imwrite(output_path, img_annotated)
            print(f"✅ Сохранено: {output_path}")
        else:
            print(f"✅ Все 4 угла найдены:")
            for cid, (x, y) in corners.items():
                print(f"   {CLASS_NAMES[cid]}: ({x}, {y})")

            # Определяем порядок углов и ориентацию
            ordered_corners, white_at_bottom = get_ordered_corners_with_orientation(
                corners, img_width, img_height
            )
            
            print(f"📐 Ориентация: белая сторона {'внизу' if white_at_bottom else 'вверху'}")

            # Perspective Transform
            output_size = 900
            padding = 50
            warped_board, M = apply_perspective_transform(img, ordered_corners, output_size, padding)

            # Рисуем сетку
            warped_with_grid = draw_8x8_grid(
                warped_board.copy(), output_size, padding, 
                color=(0, 255, 255), thickness=1, white_at_bottom=white_at_bottom
            )

            # Переносим фигуры
            if os.path.exists(label_path):
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for line in lines:
                    parts = line.strip().split()
                    if len(parts) != 5:
                        continue

                    class_id = int(parts[0])
                    # Пропускаем доску (12) и углы (13-16)
                    if class_id in [12, 13, 14, 15, 16]:
                        continue

                    x_center = float(parts[1]) * img_width
                    y_center = float(parts[2]) * img_height
                    height = float(parts[4]) * img_height

                    # Сдвигаем точку от центра вниз на 40% высоты bounding box
                    piece_x = x_center
                    piece_y = y_center + (height * 0.4)

                    # Трансформируем именно эту смещенную точку
                    point = np.float32([[[piece_x, piece_y]]])
                    transformed_point = cv2.perspectiveTransform(point, M)
                    tx, ty = transformed_point[0][0]

                    cv2.circle(warped_with_grid, (int(tx), int(ty)), 5,
                               COLORS.get(class_id, (128, 128, 128)), -1)

                    # Определяем клетку
                    col = int((tx - padding) / (output_size / 8))
                    row = int((ty - padding) / (output_size / 8))
                    col = max(0, min(7, col))
                    row = max(0, min(7, row))

                    if white_at_bottom:
                        cell_name = f"{'abcdefgh'[col]}{8 - row}"
                    else:
                        cell_name = f"{'hgfedcba'[col]}{row + 1}"
                    
                    label = CLASS_NAMES.get(class_id, "?")

                    cv2.putText(
                        warped_with_grid, f"{label}({cell_name})",
                        (int(tx) + 8, int(ty) + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        COLORS.get(class_id, (128, 128, 128)), 1
                    )

            # Собираем коллаж
            scale = 800 / img_height
            img_annotated_resized = cv2.resize(
                img_annotated,
                (int(img_width * scale), 800),
                interpolation=cv2.INTER_AREA
            )

            gap = 40
            collage_w = img_annotated_resized.shape[1] + gap + warped_board.shape[1]
            collage_h = max(800, warped_board.shape[0]) + 60

            collage = np.ones((collage_h, collage_w, 3), dtype=np.uint8) * 40

            cv2.putText(collage, "Original + BBox + Corners",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(collage, f"Perspective Transform (white {'bottom' if white_at_bottom else 'top'})",
                        (img_annotated_resized.shape[1] + gap + 10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            offset_x = img_annotated_resized.shape[1] + gap
            collage[60:60 + img_annotated_resized.shape[0], 0:img_annotated_resized.shape[1]] = img_annotated_resized
            collage[60:60 + warped_board.shape[0], offset_x:offset_x + warped_board.shape[1]] = warped_with_grid

            output_path = f"collage_corners.jpeg"
            cv2.imwrite(output_path, collage)
            print(f"✅ Коллаж сохранен: {output_path}")

            warped_path = f"warped_corners.jpeg"
            cv2.imwrite(warped_path, warped_with_grid)
            print(f"✅ Выпрямленная доска сохранена: {warped_path}")