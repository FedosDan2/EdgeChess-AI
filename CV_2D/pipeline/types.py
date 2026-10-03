from dataclasses import dataclass
from typing import Tuple


@dataclass
class BoardDetection:
    bbox: Tuple[float, float, float, float]
    confidence: float


@dataclass
class PieceDetection:
    name: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    square: str | None = None

@dataclass
class PipelineResult:
    fen: str
    board: BoardDetection
    pieces: list[PieceDetection]
    
    