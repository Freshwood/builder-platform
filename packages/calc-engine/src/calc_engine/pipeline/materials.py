"""A short list of what a module designer may use, derived from the catalog (ADR-0010).

The chat agent fetches the full price table with ``list_materials``. A module call needs far less:
ids and sizes, no prices, no finishes or consumables (the engine adds those). The text depends
only on the catalog, so it is the same for every call and stays in the provider's prompt cache.
"""

from __future__ import annotations

from calc_engine.catalog import Catalog, CatalogItem

# Added by the engine (finish, glue, screws, anchors) or chosen by the skeleton (finish).
_SKIPPED_KINDS = {"finish"}
_SKIPPED_IDS = {"glue_d3_750", "wall_anchor_set"}


def _fixed(item: CatalogItem) -> str:
    assert item.size_mm is not None
    return f"{item.id} {'x'.join(str(v) for v in item.size_mm)}"


def digest(catalog: Catalog) -> str:
    """Catalog items grouped by how a part uses them, as compact text."""
    linear: list[str] = []
    sheets: list[str] = []
    placeable: list[str] = []
    hardware: list[str] = []
    bulk: list[str] = []
    for item in catalog.items:
        if not item.designable or item.kind in _SKIPPED_KINDS or item.id in _SKIPPED_IDS:
            continue
        if item.kind == "linear":
            linear.append(item.id)
        elif item.kind == "sheet" and item.sheet_mm:
            sheets.append(f"{item.id} {item.sheet_mm[0]}x{item.sheet_mm[1]}")
        elif item.kind == "bulk":
            bulk.append(item.id)
        elif item.size_mm:
            placeable.append(_fixed(item))
        else:
            hardware.append(item.id)
    rules = catalog.lumber
    species = ", ".join(sorted(catalog.lumber_species()))
    return "\n".join(
        [
            "Katalog (Maße in mm):",
            f"- Maßholz lumber_<holzart>_<stärke>x<breite>, Stärke {rules.min_thickness_mm}–"
            f"{rules.max_thickness_mm}, Breite ≤ {rules.max_width_mm}; Holzarten: {species}",
            "- Hölzer: " + ", ".join(linear),
            "- Platten (Format): " + ", ".join(sheets),
            "- Teile mit festem Maß (als Bauteil platzieren): " + ", ".join(placeable),
            "- Beschläge (unter hardware mit Menge): " + ", ".join(hardware),
            "- Flächenmaterial nur bei Gebäuden: " + ", ".join(bulk),
        ]
    )
