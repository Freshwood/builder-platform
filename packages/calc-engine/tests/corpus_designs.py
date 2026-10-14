"""Free-form constructions in the corpus: what customers actually ask for.

These are designs the agent writes itself, not templates or packs, so they cover what the shipped
designs do not: a birdhouse with a hole and a roof, a podium whose top switches between boards
and a panel (docs/problems/bug.md), angled bars, cutouts and optional parts.

Every design here has to satisfy the engine's own checks - no collisions, connected, standing on
the floor - as well as the corpus invariants. A design that does not build is not a test case,
it is a broken fixture; ``test_corpus.py`` fails loudly on both.

Lumber needs two of its three dimensions to equal the section of the chosen material, which is
the mistake models make most often; every design below is written to that rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Nistkasten: Boden, Wände, Dach mit Überstand, Einflugloch.
BIRDHOUSE: dict[str, Any] = {
    "object_type": "Nistkasten",
    "summary": "Nistkasten mit Bohrung und Dachüberstand",
    "use": "outdoor",
    "params": [
        {
            "name": "width_mm",
            "label": "Breite",
            "kind": "length",
            "default": 400,
            "min": 250,
            "max": 600,
        },
        {
            "name": "depth_mm",
            "label": "Tiefe",
            "kind": "length",
            "default": 300,
            "min": 200,
            "max": 450,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 400,
            "min": 250,
            "max": 600,
        },
    ],
    "parts": [
        {
            "id": "floor",
            "name": "Boden",
            "material": "plywood_birch_18",
            "size": ["width_mm", "depth_mm", 18],
            "at": [0, 0, 0],
        },
        {
            "id": "back",
            "name": "Rückwand",
            "material": "plywood_birch_18",
            "size": ["width_mm", 18, "height_mm - 18"],
            "at": [0, "depth_mm - 18", 18],
        },
        {
            "id": "side",
            "name": "Seitenwand",
            "material": "plywood_birch_18",
            "size": [18, "depth_mm - 18", "height_mm - 18"],
            "at": ["i * (width_mm - 18)", 0, 18],
            "repeat": {"count": 2},
        },
        {
            "id": "front",
            "name": "Vorderwand",
            "material": "plywood_birch_18",
            "size": ["width_mm - 36", 18, "height_mm - 18"],
            "at": [18, 0, 18],
            "cutouts": [
                {
                    "kind": "ellipse",
                    "at": ["(width_mm - 36) / 2 - 22", "18"],
                    "size": [44, 44],
                }
            ],
        },
        {
            "id": "perch",
            "name": "Sitzbrett",
            "material": "board_spruce_18x96",
            "size": ["width_mm - 36", 96, 18],
            "at": [18, "depth_mm - 114", "height_mm - 114"],
        },
        {
            "id": "roof",
            "name": "Dach",
            "material": "plywood_birch_18",
            "size": ["width_mm + 40", "depth_mm + 40", 18],
            "at": [-20, -20, "height_mm"],
        },
    ],
}

#: Das Podest aus docs/problems/bug.md: die Oberfläche ist Bretter oder Platte, gewählt per
#: `choice` Parameter. Genau der Fall, an dem `when` auf einem Textparameter scheiterte.
#:
#: The width is a number of deck boards of 125 mm (`deck_boards`), not a free length: boards have
#: a fixed width and the engine rejects a trimmed board of a different cross-section, so any other
#: width would leave a gap or overhang (ceil(1000 / 146) boards of 146 mm are 1022 mm). Both
#: surfaces use the same width, `deck_boards * 125`, so the boards and the panel option are equally
#: wide for every valid value. The golden design of the regression case `podium_kids_catwalk` is
#: the JSON file below, so there is one source of truth.
PODIUM_GOLDEN_FILE = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "api"
    / "tests"
    / "regressions"
    / "podium_kids_catwalk"
    / "golden.json"
)
PODIUM: dict[str, Any] = json.loads(PODIUM_GOLDEN_FILE.read_text(encoding="utf-8"))

#: Werkbank mit Rahmen und zwei Ebenen.
WORKBENCH_FREE: dict[str, Any] = {
    "object_type": "Werkbank",
    "summary": "Werkbank mit Rahmen und Ablage",
    "params": [
        {
            "name": "width_mm",
            "label": "Breite",
            "kind": "length",
            "default": 1200,
            "min": 800,
            "max": 2000,
        },
        {
            "name": "depth_mm",
            "label": "Tiefe",
            "kind": "length",
            "default": 600,
            "min": 450,
            "max": 900,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 850,
            "min": 700,
            "max": 1000,
        },
    ],
    "parts": [
        {
            "id": "leg",
            "name": "Bein",
            "material": "square_spruce_70x70",
            "size": [70, 70, "height_mm - 24"],
            "at": [
                "i % 2 * (width_mm - 70)",
                "i // 2 * (depth_mm - 70)",
                0,
            ],
            "repeat": {"count": 4},
        },
        {
            "id": "rail",
            "name": "Traverse",
            "material": "frame_spruce_44x44",
            "size": [44, "depth_mm - 70", 44],
            "at": ["70 + i * (width_mm - 184)", 0, "height_mm - 68"],
            "repeat": {"count": 2},
        },
        {
            "id": "shelf",
            "name": "Ablageboden",
            "material": "plywood_birch_18",
            "size": ["width_mm - 140", "depth_mm - 70", 18],
            "at": [70, 0, "height_mm - 86"],
        },
        {
            "id": "top",
            "name": "Arbeitsplatte",
            "material": "plywood_birch_24",
            "size": ["width_mm", "depth_mm", 24],
            "at": [0, 0, "height_mm - 24"],
        },
    ],
}

#: Zweiflügelige Schranktür: Rahmenleisten mit Füllung, hängend an der Wand.
CUPBOARD_DOORS: dict[str, Any] = {
    "object_type": "Schranktür",
    "summary": "Zweiflügelige Schranktür aus Rahmenleisten",
    "support": "wall",
    "params": [
        {
            "name": "width_mm",
            "label": "Breite beider Flügel",
            "kind": "length",
            "default": 900,
            "min": 500,
            "max": 1400,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 1200,
            "min": 600,
            "max": 2000,
        },
    ],
    "parts": [
        {
            "id": "stile",
            "name": "Stiel",
            "material": "board_spruce_18x96",
            "size": [96, 18, "height_mm"],
            "at": ["i * ((width_mm - 384) / 3 + 96)", 0, 0],
            "repeat": {"count": 4},
        },
        {
            "id": "rail_top",
            "name": "Sturz",
            "material": "board_spruce_18x96",
            "size": ["(width_mm - 384) / 3", 18, 96],
            "at": ["96 + i * ((width_mm - 384) / 3 + 96)", 0, "height_mm - 96"],
            "repeat": {"count": 3},
        },
        {
            "id": "rail_bottom",
            "name": "Unterfries",
            "material": "board_spruce_18x96",
            "size": ["(width_mm - 384) / 3", 18, 96],
            "at": ["96 + i * ((width_mm - 384) / 3 + 96)", 0, 0],
            "repeat": {"count": 3},
        },
        {
            "id": "panel",
            "name": "Füllung",
            "material": "plywood_birch_12",
            "size": ["(width_mm - 384) / 3", 12, "height_mm - 192"],
            "at": ["96 + i * ((width_mm - 384) / 3 + 96)", 0, 96],
            "repeat": {"count": 3},
        },
    ],
}

#: Gartenbank mit Lattenlehne und Querstrebe.
GARDEN_BANK_FREE: dict[str, Any] = {
    "object_type": "Gartenbank",
    "summary": "Gartenbank mit Lattenlehne",
    "use": "outdoor",
    "params": [
        {
            "name": "length_mm",
            "label": "Länge",
            "kind": "length",
            "default": 1500,
            "min": 1000,
            "max": 2200,
        },
        {
            "name": "depth_mm",
            "label": "Tiefe",
            "kind": "length",
            "default": 550,
            "min": 505,
            "max": 700,
        },
        {
            "name": "height_mm",
            "label": "Sitzhöhe",
            "kind": "length",
            "default": 450,
            "min": 380,
            "max": 550,
        },
    ],
    "parts": [
        {
            "id": "leg_front",
            "name": "Vorderbein",
            "material": "square_larch_70x70",
            "size": [70, 70, "height_mm - 28"],
            "at": ["i * (length_mm - 70)", 0, 0],
            "repeat": {"count": 2},
        },
        {
            "id": "leg_back",
            "name": "Hinterbein",
            "material": "square_larch_70x70",
            "size": [70, 70, "height_mm + 400 - 28"],
            "at": ["i * (length_mm - 70)", "depth_mm - 70", 0],
            "repeat": {"count": 2},
        },
        {
            "id": "seat",
            "name": "Sitzlatte",
            "material": "board_larch_28x145",
            "size": ["length_mm", 145, 28],
            # Three slats spread over the seat so the last one always touches the back legs;
            # at a fixed 145 mm pitch they only touch at the minimum depth.
            "at": [0, "i * (depth_mm - 215) / 2", "height_mm - 28"],
            "repeat": {"count": 3},
        },
        {
            "id": "back_rail",
            "name": "Lehnenbrett",
            "material": "board_larch_28x145",
            "size": ["length_mm", 28, 145],
            "at": [0, "depth_mm - 28", "height_mm + 372"],
        },
        {
            "id": "stretcher",
            "name": "Strebe",
            "material": "frame_larch_45x70",
            "size": [45, "depth_mm - 70", 70],
            "at": ["length_mm / 2 - 22", 0, "height_mm - 98"],
        },
    ],
}

#: Regal aus Brettern mit variabler Fachzahl.
SHELF_BOARDS: dict[str, Any] = {
    "object_type": "Regal",
    "summary": "Bretterregal mit variablem Fachabstand",
    "params": [
        {
            "name": "width_mm",
            "label": "Breite",
            "kind": "length",
            "default": 800,
            "min": 400,
            "max": 1500,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 1200,
            "min": 600,
            "max": 2200,
        },
        {
            "name": "shelves",
            "label": "Fächer",
            "kind": "count",
            "default": 5,
            "min": 2,
            "max": 8,
        },
    ],
    "parts": [
        {
            "id": "side",
            "name": "Seitenwange",
            "material": "plywood_birch_18",
            "size": [18, 280, "height_mm"],
            "at": ["i * (width_mm - 18)", 0, 0],
            "repeat": {"count": 2},
        },
        {
            "id": "shelf",
            "name": "Einlegeboden",
            "material": "board_spruce_18x146",
            "size": ["width_mm - 36", 146, 18],
            "at": [18, 67, "i * ((height_mm - 18) / (shelves - 1))"],
            "repeat": {"count": "shelves"},
        },
    ],
}

#: Kaninchenstall mit Pfosten, Wänden und geneigtem Dach.
RABBIT_HOUSE: dict[str, Any] = {
    "object_type": "Kaninchenstall",
    "summary": "Kaninchenstall mit geneigtem Dach",
    "use": "outdoor",
    "params": [
        {
            "name": "width_mm",
            "label": "Breite",
            "kind": "length",
            "default": 1000,
            "min": 600,
            "max": 1600,
        },
        {
            "name": "depth_mm",
            "label": "Tiefe",
            "kind": "length",
            "default": 700,
            "min": 500,
            "max": 1000,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 600,
            "min": 400,
            "max": 900,
        },
    ],
    "parts": [
        {
            "id": "post",
            "name": "Pfosten",
            "material": "square_larch_70x70",
            "size": [70, 70, "height_mm"],
            "at": [
                "i % 2 * (width_mm - 70)",
                "i // 2 * (depth_mm - 70)",
                0,
            ],
            "repeat": {"count": 4},
        },
        {
            "id": "wall_long",
            "name": "Längswand",
            "material": "board_larch_28x145",
            "size": ["width_mm", 28, 145],
            "at": [0, "70 + i * (depth_mm - 168)", "height_mm - 18 - 145"],
            "repeat": {"count": 2},
        },
        {
            "id": "roof",
            "name": "Dach",
            "material": "plywood_birch_18",
            "size": ["width_mm + 40", "depth_mm + 40", 18],
            "at": [-20, -20, "height_mm"],
        },
    ],
}

#: Blumenbank mit angewinkelten Streben - Stäbe statt Quader, mit Neigung.
FLOWER_BENCH: dict[str, Any] = {
    "object_type": "Blumenbank",
    "summary": "Blumenbank mit zwei Beinen und Querstrebe",
    "use": "outdoor",
    "params": [
        {
            "name": "length_mm",
            "label": "Länge",
            "kind": "length",
            "default": 1200,
            "min": 800,
            "max": 2000,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 450,
            "min": 300,
            "max": 700,
        },
    ],
    "parts": [
        {
            "id": "leg",
            "name": "Bein",
            "material": "square_larch_70x70",
            "size": [70, 70, "height_mm - 28"],
            "at": ["i * (length_mm - 70)", 0, 0],
            "repeat": {"count": 2},
        },
        {
            "id": "seat",
            "name": "Sitzbrett",
            "material": "board_larch_28x145",
            "size": ["length_mm", 145, 28],
            "at": [0, "i * 145", "height_mm - 28"],
            "repeat": {"count": 3},
        },
        {
            "id": "stretcher",
            "name": "Querstrebe",
            "material": "frame_larch_45x70",
            "size": [45, 290, 70],
            "at": ["length_mm - 115", 0, "height_mm - 98"],
        },
    ],
}

DESIGNS: tuple[dict[str, Any], ...] = (
    BIRDHOUSE,
    PODIUM,
    WORKBENCH_FREE,
    CUPBOARD_DOORS,
    GARDEN_BANK_FREE,
    SHELF_BOARDS,
    RABBIT_HOUSE,
    FLOWER_BENCH,
)

#: Free-form designs swept by ``corpus.design_cases``; the name the corpus gives the family.
EXTRA_DESIGNS: dict[str, dict[str, Any]] = {
    "birdhouse": BIRDHOUSE,
    "workbench_free": WORKBENCH_FREE,
    "cupboard_doors": CUPBOARD_DOORS,
    "garden_bank_free": GARDEN_BANK_FREE,
    "shelf_boards": SHELF_BOARDS,
    "rabbit_house": RABBIT_HOUSE,
    "flower_bench": FLOWER_BENCH,
}


@dataclass(frozen=True)
class BugRegression:
    """A construction that once failed for a user, pinned to the parameters of the report.

    Either ``design`` (a free-form design dict) or ``fixture`` (the key of a fixture design)
    names what was built. ``params`` are the values from the report; the corpus builds exactly
    these first and then sweeps the design like any other, so the regression is never narrower
    than the family it belongs to.
    """

    report: str
    design: dict[str, Any] | None = None
    fixture: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


#: Regressions by the bug report they came from. Key = case name (``bug:<name>``).
DESIGNS_FROM_BUGS: dict[str, BugRegression] = {
    # docs/problems/bug.md: "Podest für Kinder, 2 m x 1 m, Oberfläche Bretter oder Platte". The
    # agent could not use a text parameter in `when`, and the assistant looped on it.
    "podium": BugRegression(
        report="docs/problems/bug.md",
        design=PODIUM,
        params={"length_mm": 2000, "deck_boards": 8, "height_mm": 350, "surface": "boards"},
    ),
    "podium_panel": BugRegression(
        report="docs/problems/bug.md",
        design=PODIUM,
        params={"length_mm": 2000, "deck_boards": 8, "height_mm": 350, "surface": "panel"},
    ),
    # test_assembly.py::test_window_shutter_matches_the_reported_case: 31 x 38 cm,
    # two wings of boards with hinges and a latch.
    "window_shutter": BugRegression(
        report="packages/calc-engine/tests/test_assembly.py (Fensterladen 31 x 38 cm)",
        fixture="window_shutter",
        params={"width_mm": 310, "height_mm": 380, "wings": 2, "board_mm": 18},
    ),
}
