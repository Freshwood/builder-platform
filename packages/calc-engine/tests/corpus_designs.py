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
PODIUM: dict[str, Any] = {
    "object_type": "Podest",
    "summary": "Podest für eine Modenschau, Oberfläche wählbar",
    "params": [
        {
            "name": "length_mm",
            "label": "Länge",
            "kind": "length",
            "default": 2000,
            "min": 800,
            "max": 3000,
        },
        {
            "name": "width_mm",
            "label": "Breite",
            "kind": "length",
            "default": 1000,
            "min": 600,
            "max": 1500,
        },
        {
            "name": "height_mm",
            "label": "Höhe",
            "kind": "length",
            "default": 350,
            "min": 200,
            "max": 600,
        },
        {
            "name": "surface",
            "label": "Oberfläche",
            "kind": "choice",
            "default": "boards",
            "options": [
                {"value": "boards", "label": "Einzelne Bretter"},
                {"value": "panel", "label": "Platte"},
            ],
        },
        {
            "name": "toe_board",
            "label": "Verschalung vorne",
            "kind": "bool",
            "default": True,
        },
    ],
    "parts": [
        {
            "id": "leg",
            "name": "Bein",
            "material": "frame_spruce_44x44",
            "size": [44, 44, "height_mm - 18"],
            "at": [
                "i % 2 * (length_mm - 44)",
                "i // 2 * (width_mm - 44)",
                0,
            ],
            "repeat": {"count": 4},
        },
        {
            "id": "frame_long",
            "name": "Längszarge",
            "material": "frame_spruce_44x44",
            "size": ["length_mm - 88", 44, 44],
            "at": [44, "i * (width_mm - 44)", "height_mm - 62"],
            "repeat": {"count": 2},
        },
        {
            "id": "top_boards",
            "name": "Deckbrett",
            "material": "board_spruce_18x146",
            "size": ["length_mm", 146, 18],
            "at": [0, "i * 146", "height_mm - 18"],
            "repeat": {"count": "ceil(width_mm / 146)"},
            "when": "surface == 'boards'",
        },
        {
            "id": "top_panel",
            "name": "Platte",
            "material": "plywood_birch_18",
            "size": ["length_mm", "width_mm", 18],
            "at": [0, 0, "height_mm - 18"],
            "when": "surface == 'panel'",
        },
        {
            "id": "toe_board",
            "name": "Verschalung",
            "material": "board_spruce_18x146",
            "size": ["length_mm - 88", 146, 18],
            "at": [44, 0, "height_mm - 164"],
            "when": "toe_board",
        },
    ],
}

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
            "at": [0, "i * 145", "height_mm - 28"],
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