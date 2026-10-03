from pathlib import Path
import cv2
import numpy as np
from typing import Dict, List

from .board_detector import BoardDetector
from .pieces_detector import PiecesDetector
from .board_transformer import BoardTransformer
from .preprocessor import ImagePreprocessor
from .square_mapper import SquareMapper
from .board_state import BoardState
from .fen_builder import FENBuilder
from .types import Detection, PlacedPiece


class ChessPipeline:
    """Полный пайплайн анализа шахматной позиции."""

    def __init__(
        self,
        model_path: str,
        confidence: float = 0.5,
        output_size: int = 900,
        padding: int = 50,
    ):
        # Детекторы
        self.board_detector = BoardDetector(model_path, confidence)
        self.pieces_detector = PiecesDetector(model_path, confidence)
        
        # Трансформация и маппинг
        self.transformer = BoardTransformer(output_size, padding)
        self.square_mapper = SquareMapper(output_size, padding)
        self.preprocessor = ImagePreprocessor()
        
        # Состояние доски и FEN
        self.board_state = BoardState()
        self.fen_builder = FENBuilder()

    def process(self, image_path: str, save_results: bool = False) -> dict:
        """
        Полный пайплайн обработки изображения.
        
        Returns:
            dict с результатами
        """
        # Загрузка изображения
        img, original_size = self.preprocessor.preprocess(image_path)
        img_height, img_width = img.shape[:2]

        # 1. Детекция углов и фигур
        print("🔍 Детекция...")
        corners = self.board_detector.detect_corners(image_path)
        pieces = self.pieces_detector.detect_pieces(image_path)

        print(f"✅ Найдено: {len(corners)} углов, {len(pieces)} фигур")

        # Валидация углов
        if not self.board_detector.validate_corners(corners):
            missing = {12, 13, 14, 15} - set(corners.keys())
            raise ValueError(f"Missing corners: {missing}")

        # 2. Perspective Transform
        print("🔄 Perspective Transform...")
        ordered_corners, white_at_bottom = self.transformer.get_ordered_corners(
            corners, img_width, img_height
        )
        warped_image, transform_matrix = self.transformer.transform(img, ordered_corners)

        # 3. Рисование сетки
        print("📐 Рисование сетки...")
        warped_with_grid = self.square_mapper.draw_grid(warped_image, white_at_bottom)

        # 4. Перенос фигур на клетки
        print("📍 Перенос фигур на доску...")
        placed_pieces = self._map_pieces(pieces, transform_matrix, img_width, img_height)

        # 5. Формирование матрицы
        print("📊 Формирование матрицы...")
        self.board_state.clear()
        for piece in placed_pieces:
            self.board_state.place_piece(piece)

        # 6. Генерация FEN
        print("♟️  Генерация FEN...")
        fen = self.fen_builder.build(self.board_state)

        # Сохранение результатов
        if save_results:
            self._save_results(warped_with_grid, fen)

        return {
            "corners": corners,
            "pieces": placed_pieces,
            "warped_image": warped_with_grid,
            "board_state": self.board_state,
            "fen": fen,
        }

    def _map_pieces(
        self,
        pieces: List[Detection],
        matrix: np.ndarray,
        img_width: int,
        img_height: int,
    ) -> List[PlacedPiece]:
        """Переносит фигуры на выпрямленную доску."""
        placed_pieces: List[PlacedPiece] = []

        for piece in pieces:
            # Конвертируем в пиксели
            x_center_px = piece.x_center * img_width
            y_center_px = piece.y_center * img_height
            height_px = piece.height * img_height

            # Сдвигаем точку к основанию фигуры
            piece_x = x_center_px
            piece_y = y_center_px + (height_px * 0.4)

            # Трансформируем точку
            tx, ty = self.transformer.transform_point((piece_x, piece_y), matrix)

            # Определяем клетку
            cell, col, row = self.square_mapper.pixel_to_cell(tx, ty)

            placed_pieces.append(PlacedPiece(
                class_name=piece.class_name,
                cell=cell,
                confidence=piece.confidence,
                col=col,
                row=row,
            ))

        return placed_pieces

    def _save_results(self, warped_image: np.ndarray, fen: str):
        """Сохраняет результаты."""
        output_dir = Path("results")
        output_dir.mkdir(exist_ok=True)

        cv2.imwrite(str(output_dir / "warped_board.jpg"), warped_image)
        print(f"💾 Сохранено: {output_dir / 'warped_board.jpg'}")

        with open(output_dir / "fen.txt", "w") as f:
            f.write(fen)
        print(f"💾 Сохранено: {output_dir / 'fen.txt'}")