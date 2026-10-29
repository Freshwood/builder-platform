"""Compact, token-friendly views of projects, changes and the material catalog for the LLM."""

from __future__ import annotations

from typing import Any

from homeworking.calc_engine.catalog import Catalog
from homeworking.construction_model.diff import ModelDiff
from homeworking.construction_model.model import ProjectModel


def _eur(value: Any) -> str:
    return f"{value:.0f} €"


def project_summary(model: ProjectModel, *, with_bom: bool = False) -> dict[str, Any]:
    """Compact, token-friendly view of a project for the LLM.

    The bill of materials (about half of the summary) is only included on request
    (get_project); every create/change result would otherwise repeat it in the history.
    """
    r = model.result
    summary: dict[str, Any] = {
        "project_id": str(model.id),
        "title": model.inputs.title,
        "summary": r.summary,
        "params": r.effective_params,
        "adjustable": [
            {
                k: v
                for k, v in {
                    "name": p.name,
                    "label": p.label,
                    "min": p.min,
                    "max": p.max,
                    "options": [o.value for o in p.options] or None,
                }.items()
                if v is not None
            }
            for p in r.param_specs
        ],
        "key_figures": r.key_figures,
        "material_cost_eur": f"{_eur(r.costs.material.min)} – {_eur(r.costs.material.max)}",
        "material_used_eur": (
            f"{_eur(r.costs.material_used.min)} – {_eur(r.costs.material_used.max)}"
            if r.costs.material_used
            else None
        ),
        "prices": (
            f"{r.costs.user_priced} von {len(r.bom)} Positionen mit Nutzerpreis, Rest Richtpreise"
        ),
        "variants": [
            {
                "key": v.key,
                "name": v.name,
                "description": v.description,
                "material_cost_eur": f"{_eur(v.material_cost.min)} – {_eur(v.material_cost.max)}",
                "selected": v.is_selected,
            }
            for v in r.variants
        ],
        "notices": [n.message for n in r.notices],
    }
    if with_bom:
        summary["bom"] = [
            {
                "item_id": line.item_id,
                "name": f"{line.name} ({line.spec})",
                "quantity": f"{line.quantity:f} {line.unit}",
                "unit_price_eur": f"{line.unit_price.min}–{line.unit_price.max}",
                "source": line.price_source,
            }
            for line in r.bom
        ]
    return summary


def diff_summary(diff: ModelDiff) -> dict[str, Any]:
    out: dict[str, Any] = {
        "changed_params": {c.name: {"before": c.before, "after": c.after} for c in diff.params},
        "changed_figures": {
            c.name: {"before": c.before, "after": c.after} for c in diff.key_figures
        },
    }
    if diff.material_cost_before:
        out["material_cost_before_eur"] = (
            f"{_eur(diff.material_cost_before[0])} – {_eur(diff.material_cost_before[1])}"
        )
    out["material_cost_after_eur"] = (
        f"{_eur(diff.material_cost_after[0])} – {_eur(diff.material_cost_after[1])}"
    )
    return out


def design_materials(catalog: Catalog) -> dict[str, Any]:
    """Materials usable in free-form designs, in a compact form for the LLM."""
    items: list[dict[str, Any]] = []
    for item in catalog.items:
        if not item.designable:
            continue
        entry: dict[str, Any] = {"id": item.id, "name": item.name, "kind": item.kind}
        if item.kind == "linear" and item.section_mm:
            entry["section_mm"] = list(item.section_mm)
            entry["max_length_mm"] = max(item.stock_lengths_mm)
            entry["eur_per_m"] = f"{item.price_min}–{item.price_max}"
        elif item.kind == "sheet" and item.sheet_mm:
            entry["thickness_mm"] = item.thickness_mm
            entry["sheet_mm"] = list(item.sheet_mm)
            entry["eur_per_sheet"] = f"{item.price_min}–{item.price_max}"
        elif item.size_mm:
            entry["fixed_size_mm"] = list(item.size_mm)
            entry["placeable"] = True
        else:
            entry["use"] = "finish" if item.kind == "finish" else "hardware"
        if item.hardware_type:
            entry["hardware_type"] = item.hardware_type
        entry["outdoor"] = item.outdoor
        items.append(entry)
    rules = catalog.lumber
    lumber = {
        "id_format": "lumber_<species>_<thickness>x<width>",
        "example": "lumber_douglas_18x96",
        "explanation": (
            "Made-to-order lumber: every species below is available in ANY cross-section "
            "(boards, battens, beams). Use it whenever the catalog items above do not have the "
            "species or section the user wants. Price is derived from the wood volume."
        ),
        "thickness_mm": [rules.min_thickness_mm, rules.max_thickness_mm],
        "max_width_mm": rules.max_width_mm,
        "species": [
            {
                "species": key,
                "label": m.label,
                "eur_per_m3": f"{m.lumber_price_m3[0]}–{m.lumber_price_m3[1]}",
                "max_length_mm": max(m.lumber_stock_lengths_mm or [3000]),
                "outdoor": m.outdoor,
            }
            for key, m in catalog.lumber_species().items()
            if m.lumber_price_m3
        ],
    }
    return {"catalog_items": items, "lumber": lumber}


def materials_table(catalog: Catalog) -> str:
    """The design materials as a compact text table (about a third of the JSON tokens)."""
    data = design_materials(catalog)
    lines = ["Katalog: id | Name | Maße mm | Preis € | außen | Beschlagtyp"]
    for e in data["catalog_items"]:
        if "section_mm" in e:
            size = f"{e['section_mm'][0]}x{e['section_mm'][1]} ≤{e['max_length_mm']}"
            price = f"{e['eur_per_m']}/m"
        elif "sheet_mm" in e:
            size = f"{e['thickness_mm']} Platte {e['sheet_mm'][0]}x{e['sheet_mm'][1]}"
            price = f"{e['eur_per_sheet']}/Platte"
        elif "fixed_size_mm" in e:
            size = "fest " + "x".join(str(v) for v in e["fixed_size_mm"])
            price = ""
        else:
            size, price = e["use"], ""
        outdoor = "ja" if e["outdoor"] else "nein"
        lines.append(
            f"{e['id']} | {e['name']} | {size} | {price} | {outdoor} | {e.get('hardware_type', '')}"
        )
    lumber = data["lumber"]
    lines += [
        "",
        f"Maßholz {lumber['id_format']} (z. B. {lumber['example']}): jede Holzart in JEDEM "
        f"Querschnitt, Stärke {lumber['thickness_mm'][0]}–{lumber['thickness_mm'][1]} mm, "
        f"Breite ≤{lumber['max_width_mm']} mm; nehmen, wenn kein Katalogartikel passt.",
        "species | Name | €/m³ | max Länge mm | außen",
        *(
            f"{sp['species']} | {sp['label']} | {sp['eur_per_m3']} | {sp['max_length_mm']} | "
            f"{'ja' if sp['outdoor'] else 'nein'}"
            for sp in lumber["species"]
        ),
    ]
    return "\n".join(lines)
