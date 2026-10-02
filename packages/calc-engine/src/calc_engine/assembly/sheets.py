"""Two-dimensional sheet cutting (shelf heuristic, deterministic)."""

from __future__ import annotations

from dataclasses import dataclass, field

KERF_MM = 4


@dataclass
class _Shelf:
    height: int
    used: int = 0


@dataclass
class SheetLayout:
    length: int
    width: int
    shelves: list[_Shelf] = field(default_factory=list)
    used_area: int = 0

    def place(self, piece: tuple[int, int]) -> bool:
        a, b = piece
        for long, short in ((a, b), (b, a)):
            if long > self.length or short > self.width:
                continue
            for shelf in self.shelves:
                extra = KERF_MM if shelf.used else 0
                if short <= shelf.height and shelf.used + extra + long <= self.length:
                    shelf.used += extra + long
                    self.used_area += a * b
                    return True
            taken = sum(s.height for s in self.shelves) + KERF_MM * len(self.shelves)
            if taken + short <= self.width:
                self.shelves.append(_Shelf(height=short, used=long))
                self.used_area += a * b
                return True
        return False


def plan_sheets(pieces: list[tuple[int, int]], sheet: tuple[int, int]) -> list[SheetLayout]:
    """Distribute rectangular pieces onto as few sheets as the heuristic finds."""
    length, width = max(sheet), min(sheet)
    ordered = sorted(((max(p), min(p)) for p in pieces), key=lambda p: (p[1], p[0]), reverse=True)
    sheets: list[SheetLayout] = []
    for piece in ordered:
        if not any(s.place(piece) for s in sheets):
            fresh = SheetLayout(length, width)
            if not fresh.place(piece):
                raise ValueError(f"Piece {piece} does not fit on sheet {sheet}")
            sheets.append(fresh)
    return sheets
