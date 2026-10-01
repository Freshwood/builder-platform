"""One-dimensional cutting stock planning (first-fit decreasing)."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_KERF_MM = 4


@dataclass
class StockBar:
    length_mm: int
    pieces: list[int] = field(default_factory=list)
    kerf_mm: int = DEFAULT_KERF_MM

    @property
    def used_mm(self) -> int:
        return sum(self.pieces) + self.kerf_mm * max(0, len(self.pieces) - 1)

    def fits(self, piece_mm: int) -> bool:
        extra = self.kerf_mm if self.pieces else 0
        return self.used_mm + extra + piece_mm <= self.length_mm

    @property
    def waste_mm(self) -> int:
        return self.length_mm - self.used_mm


def plan_cuts(
    pieces_mm: list[int], stock_length_mm: int, kerf_mm: int = DEFAULT_KERF_MM
) -> list[StockBar]:
    """Distribute pieces over the fewest stock bars (FFD heuristic, deterministic)."""
    for piece in pieces_mm:
        if piece <= 0:
            raise ValueError("Piece lengths must be positive")
        if piece > stock_length_mm:
            raise ValueError(f"Piece of {piece} mm exceeds stock length {stock_length_mm} mm")
    bars: list[StockBar] = []
    for piece in sorted(pieces_mm, reverse=True):
        for bar in bars:
            if bar.fits(piece):
                bar.pieces.append(piece)
                break
        else:
            bars.append(StockBar(length_mm=stock_length_mm, pieces=[piece], kerf_mm=kerf_mm))
    return bars
