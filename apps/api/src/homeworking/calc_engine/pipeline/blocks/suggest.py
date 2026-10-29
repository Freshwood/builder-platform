"""Which block fits a brief? Decided by rules, never by the LLM.

A model sometimes plans a module by hand although a block covers the object, and then the slow and
unreliable path starts. When the skeleton is a single module without a block and the brief names an
object a block builds, the engine puts the block in. A skeleton with several modules, or one that
chose a block itself, is left alone.
"""

from __future__ import annotations

import re

from homeworking.calc_engine.pipeline.blocks import BlockError, expand, prepare
from homeworking.construction_model.pipeline import BlockSpec, Skeleton, Spec

# Checked in order; the first match wins. Compound words count ("Gartenhaus", "Schuhregal").
_RULES: tuple[tuple[re.Pattern[str], dict[str, object]], ...] = (
    (
        re.compile(r"carport|unterstand|überdachung|ueberdachung", re.I),
        {"kind": "post_frame", "roof": "shed"},
    ),
    (re.compile(r"pergola", re.I), {"kind": "post_frame", "roof": "flat"}),
    (re.compile(r"zaun|sichtschutz", re.I), {"kind": "fence"}),
    (
        re.compile(
            r"fachwerk|(?:garten|spiel|holz|block|wochenend|bienen|ferien)haus|(?<!hund)(?<!hunde)h(?:ü|ue)tte"
            r"|schuppen|gartenlaube|laube|(?<![a-zäöüß])haus(?![a-zäöüß])",
            re.I,
        ),
        {"kind": "house"},
    ),
    (re.compile(r"podest|b(?:ü|ue)hne|laufsteg", re.I), {"kind": "platform"}),
    (re.compile(r"werkbank|werkstatttisch", re.I), {"kind": "table", "lower_shelf": True}),
    (re.compile(r"tisch|bank\b|sitzbank|schreibtisch", re.I), {"kind": "table"}),
    (re.compile(r"schrank|kommode|sideboard", re.I), {"kind": "carcass", "doors": True}),
    (re.compile(r"regal|bücherwand|buecherwand", re.I), {"kind": "carcass"}),
)


# Wishes a block does not build (shape, fittings, special materials): the brief needs a design
# of its own, so the engine does not put a block in. A model that chose a block itself is not
# second-guessed here.
_CUSTOM = re.compile(
    r"wolke|kontur|rund|oval|herz|bogen|geschwungen|schublade|klapp|r(?:ä|ae)der|rollen"
    r"|l(?:ä|ae)den|fensterlade|glas|metall|stahl|beleucht|leimholz|glulam|sonderform|ausschnitt",
    re.IGNORECASE,
)


def suggest(description: str) -> BlockSpec | None:
    if _CUSTOM.search(description):
        return None
    for pattern, options in _RULES:
        if pattern.search(description):
            return BlockSpec.model_validate(options)
    return None


def adopt(skeleton: Skeleton, spec: Spec) -> Skeleton:
    """Put a block into a skeleton the brief clearly asks for (see the module text).

    A skeleton in which the model planned the object by hand, in one module or several, becomes
    one block module; a skeleton that uses a block already is left alone."""
    if any(m.block is not None for m in skeleton.modules):
        return skeleton
    names = {p.name for p in skeleton.params if p.kind == "length"}
    if not {"width_mm", "depth_mm", "height_mm"} <= names:
        return skeleton
    block = suggest(spec.description)
    if block is None:
        return skeleton
    first = skeleton.modules[0]
    module = first.model_copy(
        update={
            "block": block,
            "when": None,
            "origin": (0, 0, 0),
            "size": ("width_mm", "depth_mm", "height_mm"),
        }
    )
    if len(skeleton.modules) > 1:
        module = module.model_copy(update={"id": "bau", "title": skeleton.object_type[:60]})
    candidate = prepare(
        skeleton.model_copy(update={"modules": [module]}), {"width_mm", "depth_mm", "height_mm"}
    )
    env = {p.name: p.default for p in candidate.params}
    try:
        expand(candidate.modules[0], env, "larch")
    except BlockError:
        return skeleton  # the block does not fit these dimensions: the model's own plan stays
    return skeleton.model_copy(update={"modules": [module]})


_WALL = re.compile(
    r"wandregal|wandschrank|wandboard|h(?:ä|ae)ngeregal|h(?:ä|ae)ngeschrank|wandmontage"
    r"|an der wand|an die wand|wandhalterung|wandh(?:ä|ae)ngend",
    re.IGNORECASE,
)


def infer_support(description: str) -> str | None:
    """``wall`` if the brief says the object hangs on a wall (a shelf the customer calls
    "Wandregal" is wall mounted even if nobody said so), else nothing."""
    return "wall" if _WALL.search(description) else None


_OUTDOOR = re.compile(
    r"garten|drau(?:ß|ss)en|au(?:ß|ss)en(?!ma)|terrasse|balkon|hof\b|carport|pergola|zaun|wetterfest"
    r"|hochbeet|schuppen|gartenhaus|fachwerkhaus",
    re.IGNORECASE,
)
_INDOOR = re.compile(
    r"\binnen\b|drinnen|im haus|wohnzimmer|flur|zimmer|k(?:ü|ue)che|bad\b", re.IGNORECASE
)


def infer_use(description: str) -> str | None:
    """``outdoor`` or ``indoor`` where the brief says so ("Gartentisch", "im Flur"), else nothing.
    Indoor words win: "Regal im Gartenhaus-Modell fürs Kinderzimmer" is indoors."""
    if _INDOOR.search(description):
        return "indoor"
    return "outdoor" if _OUTDOOR.search(description) else None
