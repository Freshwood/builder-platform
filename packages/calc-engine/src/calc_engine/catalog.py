"""Material and tool catalog with indicative price ranges."""

from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from construction_model.model import BomLine, Money

CENT = Decimal("0.01")
LUMBER_PREFIX = "lumber_"
_LUMBER_ID = re.compile(r"^lumber_([a-z_]+?)_(\d{1,3})x(\d{1,3})$")
_LUMBER_SPECIES = re.compile(r"^lumber_([a-z_]+)$")
HardwareType = Literal["hinge", "latch", "handle", "bracket", "castor"]


class CatalogItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    spec: str
    unit: str
    price_min: Decimal
    price_max: Decimal
    category: str
    # Fields used by free-form designs (ADR-0004). For ``linear`` items the price is per metre.
    kind: Literal["piece", "linear", "sheet", "screw", "finish", "bulk"] = "piece"
    material: str | None = None
    section_mm: tuple[int, int] | None = Field(None, description="Linear: thickness × width")
    stock_lengths_mm: list[int] = Field(default_factory=list)
    sheet_mm: tuple[int, int] | None = Field(None, description="Sheet: length × width")
    thickness_mm: int | None = None
    size_mm: tuple[int, int, int] | None = Field(None, description="Placeable piece: x × y × z")
    screw_length_mm: int | None = None
    pack_size: int | None = None
    coverage_m2: Decimal | None = Field(None, description="Finish: area per unit and coat")
    outdoor: bool = False
    designable: bool = Field(False, description="Offered to the LLM for free-form designs")
    hardware_type: HardwareType | None = Field(
        None, description="Function of a hardware piece, e.g. hinge or latch"
    )
    made_to_order: bool = Field(False, description="Lumber cut to any section (``lumber_…``)")
    bulk_basis: Literal["area", "volume"] | None = Field(
        None, description="Bulk: priced per m² of face area or per m³ of volume"
    )
    thickness_range_mm: tuple[int, int] | None = Field(
        None, description="Bulk: allowed layer thickness (min, max)"
    )


class MaterialInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    tone: str
    density_kg_m3: int
    outdoor: bool
    lumber_price_m3: tuple[Decimal, Decimal] | None = Field(
        None, description="Price range per m³ of planed lumber; enables ``lumber_…`` ids"
    )
    lumber_stock_lengths_mm: list[int] = Field(default_factory=list)


class LumberRules(BaseModel):
    """Bounds for made-to-order lumber: every species with a m³ price in any section."""

    model_config = ConfigDict(frozen=True)

    note: str = ""
    min_thickness_mm: int = 8
    max_thickness_mm: int = 200
    max_width_mm: int = 400


def lumber_id(species: str, thickness_mm: int, width_mm: int) -> str:
    t, w = sorted((thickness_mm, width_mm))
    return f"{LUMBER_PREFIX}{species}_{t}x{w}"


def _lumber_kind(t: int, w: int) -> str:
    """German trade name of a section (t ≤ w)."""
    if t < 40:
        return "Leiste" if w <= 60 else "Brett"
    if w >= 2.5 * t:
        return "Bohle"
    return "Kantholz"


class CatalogTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    price_min: Decimal
    price_max: Decimal


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    as_of: str
    note: str
    items: list[CatalogItem]
    tools: list[CatalogTool]
    materials: dict[str, MaterialInfo] = Field(default_factory=dict)
    lumber: LumberRules = Field(default_factory=LumberRules)

    def item(self, item_id: str) -> CatalogItem:
        item = self.find(item_id)
        if item is None:
            raise KeyError(f"Catalog item '{item_id}' not found")
        return item

    def find(self, item_id: str) -> CatalogItem | None:
        found = next((item for item in self.items if item.id == item_id), None)
        if found is None and item_id.startswith(LUMBER_PREFIX):
            lumber = self.resolve_lumber(item_id)
            return lumber if isinstance(lumber, CatalogItem) else None
        return found

    def lumber_species(self) -> dict[str, MaterialInfo]:
        return {k: m for k, m in self.materials.items() if m.lumber_price_m3}

    def resolve_lumber(
        self, item_id: str, size: tuple[float, float, float] | None = None
    ) -> CatalogItem | str:
        """Made-to-order lumber; returns an error text if invalid.

        ``lumber_<species>_<t>x<w>`` has a fixed section. ``lumber_<species>`` takes the section
        from the two smaller dimensions of ``size`` (the part), so it can follow parameters.
        """
        match = _LUMBER_ID.match(item_id)
        species_only = _LUMBER_SPECIES.match(item_id)
        if match is not None:
            species, a, b = match.group(1), int(match.group(2)), int(match.group(3))
        elif species_only is not None and size is not None:
            d0, d1, _ = sorted(size)
            species, a, b = species_only.group(1), round(d0), round(d1)
        else:
            return (
                f"'{item_id}' hat nicht das Format lumber_<holzart>_<stärke>x<breite> "
                "(z. B. lumber_douglas_18x96) bzw. lumber_<holzart>"
            )
        material = self.lumber_species().get(species)
        if material is None or material.lumber_price_m3 is None:
            known = ", ".join(sorted(self.lumber_species()))
            return f"Holzart '{species}' ist unbekannt (verfügbar: {known})"
        t, w = sorted((a, b))
        rules = self.lumber
        if t < rules.min_thickness_mm or t > rules.max_thickness_mm or w > rules.max_width_mm:
            return (
                f"Querschnitt {t} × {w} mm ist nicht lieferbar (Stärke {rules.min_thickness_mm}–"
                f"{rules.max_thickness_mm} mm, Breite bis {rules.max_width_mm} mm)"
            )
        m3_per_m = Decimal(t * w) / Decimal(1_000_000)
        low, high = material.lumber_price_m3
        return CatalogItem(
            id=lumber_id(species, t, w),
            name=f"{_lumber_kind(t, w)} {material.label}, gehobelt",
            spec=f"{t} × {w} mm",
            unit="m",
            price_min=(low * m3_per_m).quantize(CENT, ROUND_HALF_UP),
            price_max=(high * m3_per_m).quantize(CENT, ROUND_HALF_UP),
            category="wood",
            kind="linear",
            material=species,
            section_mm=(t, w),
            stock_lengths_mm=material.lumber_stock_lengths_mm or [2000, 2500, 3000],
            outdoor=material.outdoor,
            designable=True,
            made_to_order=True,
        )

    def tool(self, tool_id: str) -> CatalogTool:
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        raise KeyError(f"Catalog tool '{tool_id}' not found")


@cache
def default_catalog() -> Catalog:
    raw = resources.files("calc_engine").joinpath("data/catalog.json").read_text("utf-8")
    return Catalog.model_validate(json.loads(raw))


def money(min_: Decimal, max_: Decimal) -> Money:
    return Money(min=min_.quantize(CENT, ROUND_HALF_UP), max=max_.quantize(CENT, ROUND_HALF_UP))


def sum_money(values: list[Money]) -> Money:
    return money(sum((v.min for v in values), Decimal(0)), sum((v.max for v in values), Decimal(0)))


_QUERY_NOISE = re.compile(
    r"\s*\b(?:Packung|je|ca\.|inkl\.|mit Kloben|einseitig|unbehandelt|gehobelt|glatt)(?=\s|$).*$",
    re.IGNORECASE,
)
_QUERY_LABELS = re.compile(r"\b(Länge|Breite|Rad|Lochabstand)\s+", re.IGNORECASE)


def search_query(name: str, spec: str) -> str:
    """Short product search text for retailer websites, e.g. 'Leimholzplatte Fichte 18 mm'."""
    # ", " separates spec parts; a bare comma is a decimal comma ("0,75 l").
    base = re.split(r", | \(", name)[0].strip()
    first = _QUERY_LABELS.sub("", _QUERY_NOISE.sub("", spec.split(", ")[0])).strip()
    return f"{base} {first}".strip()


def _share(used: Decimal | float | None, quantity: Decimal) -> Decimal | None:
    if used is None or quantity <= 0:
        return None
    share = Decimal(str(used)) / quantity
    return min(Decimal(1), share).quantize(Decimal("0.001"), ROUND_HALF_UP)


class BomBuilder:
    """Collects BOM lines in insertion order and prices them from the catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._lines: list[BomLine] = []

    def add(
        self,
        item_id: str,
        quantity: int | Decimal,
        note: str | None = None,
        used: Decimal | float | None = None,
    ) -> None:
        """Add a catalog item; ``used`` is the consumed quantity if less than bought (packs)."""
        if quantity <= 0:
            return
        item = self._catalog.item(item_id)
        qty = Decimal(quantity)
        self._lines.append(
            BomLine(
                position=len(self._lines) + 1,
                item_id=item.id,
                name=item.name,
                spec=item.spec,
                quantity=qty,
                unit=item.unit,
                unit_price=money(item.price_min, item.price_max),
                total=money(item.price_min * qty, item.price_max * qty),
                note=note,
                used_share=_share(used, qty),
                search_query=search_query(item.name, item.spec),
            )
        )

    def add_custom(
        self,
        item_id: str,
        name: str,
        spec: str,
        quantity: int | Decimal,
        unit: str,
        unit_min: Decimal,
        unit_max: Decimal,
        note: str | None = None,
    ) -> None:
        """Add a line with an explicitly computed unit price (e.g. a stock length of a profile)."""
        if quantity <= 0:
            return
        qty = Decimal(quantity)
        self._lines.append(
            BomLine(
                position=len(self._lines) + 1,
                item_id=item_id,
                name=name,
                spec=spec,
                quantity=qty,
                unit=unit,
                unit_price=money(unit_min, unit_max),
                total=money(unit_min * qty, unit_max * qty),
                note=note,
                search_query=search_query(name, spec),
            )
        )

    @property
    def lines(self) -> list[BomLine]:
        return list(self._lines)

    def total(self) -> Money:
        return sum_money([line.total for line in self._lines])
