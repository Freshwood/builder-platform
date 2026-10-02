"""Parameters of the raised bed pack (all lengths in mm, outer dimensions)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Wood(StrEnum):
    SPRUCE = "spruce"
    DOUGLAS = "douglas"
    LARCH = "larch"


WOOD_LABELS: dict[Wood, str] = {
    Wood.SPRUCE: "Fichte",
    Wood.DOUGLAS: "Douglasie",
    Wood.LARCH: "Lärche",
}


class RaisedBedParams(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    length_mm: int = Field(
        2000, ge=600, le=4000, title="Länge außen (mm)", description="Außenlänge 600–4000 mm"
    )
    width_mm: int = Field(
        1000, ge=400, le=1500, title="Breite außen (mm)", description="Außenbreite 400–1500 mm"
    )
    height_mm: int = Field(
        800,
        ge=290,
        le=1160,
        title="Höhe (mm)",
        description="Gewünschte Wandhöhe 290–1160 mm; wird auf ganze Brettreihen (145 mm) aufgerundet",
    )
    wood: Wood = Field(
        Wood.DOUGLAS,
        title="Holzart",
        json_schema_extra={"option_labels": {w.value: label for w, label in WOOD_LABELS.items()}},
    )
    liner: bool = Field(True, title="Noppenbahn innen")
    vole_mesh: bool = Field(True, title="Wühlmausgitter")
    top_cap: bool = Field(False, title="Abdeckleiste / Sitzkante")
