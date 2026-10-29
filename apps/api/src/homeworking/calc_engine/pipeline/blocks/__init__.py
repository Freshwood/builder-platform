"""Building blocks: modules the engine writes itself (ADR-0010 follow-up).

Complex constructions (timber frame, roof, floor) fail when a small model has to place hundreds of
parts that touch face to face without overlapping. A block does that in code: the skeleton names
the block and its few options, the engine generates the parts as expressions over the design
parameters (so sliders and variants keep working) and the usual checks run over the result. A block
module costs no model call.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from homeworking.calc_engine.assembly.expr import ExprError
from homeworking.calc_engine.pipeline.blocks.frame import SHED_SPAN_MAX_MM, fence, post_frame
from homeworking.calc_engine.pipeline.blocks.furniture import STEPS as FURNITURE_STEPS
from homeworking.calc_engine.pipeline.blocks.furniture import carcass, platform, table
from homeworking.calc_engine.pipeline.blocks.house import height_bounds, house, house_limits, steps
from homeworking.calc_engine.pipeline.blocks.kit import BlockError, Ctx, Out
from homeworking.calc_engine.pipeline.blocks.sym import e
from homeworking.construction_model.assembly import ChoiceOption, DesignParam
from homeworking.construction_model.base import ParamValue
from homeworking.construction_model.pipeline import BlockSpec, ModuleBrief, ModuleDesign, Skeleton

__all__ = ["BlockError", "block_steps", "expand", "prepare", "wood_key"]

# Sliders of a block's dimensions move within this part of the default: counts (pieces, sheets) are
# sized for the upper end, and the lower end keeps every part longer than its neighbours' width.
REACH = 1.25
SHRINK = 0.75

BUILDERS = {
    "house": house,
    "carcass": carcass,
    "platform": platform,
    "table": table,
    "post_frame": post_frame,
    "fence": fence,
}
LARGE = {"house", "post_frame", "fence"}
DEFAULT_WOOD = {"outdoor": "larch", "indoor": "spruce"}


def wood_key(use: str, params: Mapping[str, ParamValue], species: set[str]) -> str:
    """The wood placeholder ``{wood}`` if the skeleton has a lumber species choice, else a default."""
    chosen = params.get("wood")
    if isinstance(chosen, str) and chosen in species:
        return "{wood}"
    return DEFAULT_WOOD.get(use, "spruce")


def normalize_block(block: BlockSpec) -> BlockSpec:
    """Fill in the options a model may leave open or mix up between blocks."""
    if block.kind == "post_frame":
        roof = "flat" if block.roof == "flat" else "shed"
    elif block.kind == "house":
        roof = "gable" if block.roof == "gable" or block.roof is None else "flat"
    else:
        return block
    return block.model_copy(update={"roof": roof})


def expand(brief: ModuleBrief, params: Mapping[str, ParamValue], wood: str) -> ModuleDesign:
    """The parts of a block module in module-local coordinates (origin = the module's corner)."""
    assert brief.block is not None
    block = normalize_block(brief.block)
    try:
        size = tuple(e(v) for v in brief.size)
        out = Out()
        ctx = Ctx(dict(params), wood, REACH, SHRINK)
        builder = BUILDERS[block.kind]
        builder(out, ctx, block, (size[0], size[1], size[2]))
    except ExprError as exc:
        raise BlockError(f"Maße des Moduls '{brief.id}': {exc}") from exc
    # Built without validation on purpose: the 40-part limit protects the model's output size, a
    # block is code and the engine checks the merged design anyway.
    return ModuleDesign.model_construct(
        module=brief.id, parts=out.parts, joints=out.joints, hardware=out.hardware
    )


# Smallest size per kind (width, depth, height) the block builds; 0 = no limit of its own.
_MINIMA = {
    "house": (2400, 2400, 0),
    "carcass": (200, 150, 150),
    "platform": (400, 400, 100),
    "table": (300, 300, 260),
    "post_frame": (1500, 1500, 2700),
    "fence": (1000, 0, 600),
}
_FURNITURE = {"carcass", "platform", "table"}

# Modules a model adds next to a block although the block already contains them (a foundation
# next to a carport collides with its posts, walls next to a house with its walls).
_INCLUDED = {
    "house": re.compile(
        r"fundament|gr[uü]ndung|bodenplatte|boden|wand|w[äa]nde|dach|sparren|fachwerk|rahmen"
        r"|gerüst|schwelle",
        re.IGNORECASE,
    ),
    "post_frame": re.compile(
        r"fundament|gr[uü]ndung|pfosten|pfette|sparren|dach|stütze|träger|rahmen|gerüst",
        re.IGNORECASE,
    ),
    "fence": re.compile(r"fundament|pfosten|riegel|latten|rahmen|gerüst", re.IGNORECASE),
}


def fit(skeleton: Skeleton, given: set[str]) -> Skeleton:
    """Move the dimensions the customer did not state into what the block can build.

    A model that has to choose usual dimensions sometimes picks a height no gable roof fits under;
    that is the engine's to correct, not a reason to ask the model again. What the customer stated
    is left alone: if that does not fit, the block says so."""
    blocks = [m for m in skeleton.modules if m.block is not None]
    if len(blocks) != 1 or len(skeleton.modules) != 1:
        return skeleton
    block = normalize_block(blocks[0].block)  # type: ignore[arg-type]
    values = {p.name: float(p.default) for p in skeleton.params if not isinstance(p.default, str)}
    if not all(n in values for n in ("width_mm", "depth_mm", "height_mm")):
        return skeleton
    minima: dict[str, float] = dict(
        zip(("width_mm", "depth_mm", "height_mm"), _MINIMA[block.kind], strict=True)
    )
    target = dict(values)
    for name, low in minima.items():
        if name not in given:
            target[name] = max(target[name], float(low))
    if block.kind == "house" and block.roof == "gable" and "height_mm" in given:
        # A stated height no gable roof fits under: a lean-to hut (flat roof) still can.
        low, _ = height_bounds(block, target["width_mm"], target["depth_mm"])
        if target["height_mm"] < low:
            block = block.model_copy(update={"roof": "flat"})
            skeleton = skeleton.model_copy(
                update={"modules": [skeleton.modules[0].model_copy(update={"block": block})]}
            )
    if block.kind == "house":
        for name in ("width_mm", "depth_mm"):
            if name not in given:
                target[name] = min(target[name], 9000.0)
        low, high = height_bounds(block, target["width_mm"], target["depth_mm"])
        if "height_mm" not in given:
            target["height_mm"] = min(
                max(target["height_mm"], float(math.ceil(low / 100) * 100)), high
            )
    if block.kind == "post_frame" and block.roof == "shed":
        span = "depth_mm" if target["width_mm"] >= target["depth_mm"] else "width_mm"
        if span not in given:
            target[span] = min(target[span], float(SHED_SPAN_MAX_MM))
    params = []
    for p in skeleton.params:
        new = target.get(p.name)
        if new is not None and new != float(p.default) and p.kind == "length":
            value = round(new)
            p = p.model_copy(
                update={
                    "default": value,
                    "min": min(p.min if p.min is not None else value, value),
                    "max": max(p.max if p.max is not None else value, value),
                }
            )
        params.append(p)
    return skeleton.model_copy(update={"params": params})


def with_surface_choice(skeleton: Skeleton) -> Skeleton:
    """A podium offers its deck as panel or boards (what a customer may ask for)."""
    surface = DesignParam(
        name="surface",
        label="Oberfläche",
        kind="choice",
        default="panel",
        options=[
            ChoiceOption(value="panel", label="Platte"),
            ChoiceOption(value="boards", label="Bretter"),
        ],
    )
    params = [p for p in skeleton.params if p.name != "surface"]
    return skeleton.model_copy(update={"params": [*params, surface]})


def prepare(skeleton: Skeleton, given: set[str] | None = None) -> Skeleton:
    """Fit a skeleton with blocks: a block that makes up the whole object takes its box from the
    three dimension parameters; a house's ranges shrink to what it can follow."""
    blocks = [m for m in skeleton.modules if m.block is not None]
    if not blocks:
        return skeleton
    whole = [m for m in blocks if m.block is not None and m.block.kind in _FURNITURE]
    if len(whole) == 1 and len(skeleton.modules) > 1:
        # A piece of furniture is one block: the model's other modules (top, frame, ...) are the
        # same object a second time.
        skeleton = skeleton.model_copy(update={"modules": whole})
        blocks = whole
    covering = [m for m in blocks if m.block is not None and m.block.kind in _INCLUDED]
    if len(covering) == 1 and covering[0].block is not None:
        pattern = _INCLUDED[covering[0].block.kind]
        keep = [
            m
            for m in skeleton.modules
            if m is covering[0] or not pattern.search(f"{m.id} {m.title}")
        ]
        skeleton = skeleton.model_copy(update={"modules": keep})
        blocks = [m for m in blocks if m in keep]
    skeleton = fit(skeleton, given or set())
    if any(m.block is not None and m.block.kind == "platform" for m in skeleton.modules):
        skeleton = with_surface_choice(skeleton)
    if any(m.block.kind in LARGE for m in blocks if m.block is not None):
        skeleton = skeleton.model_copy(update={"category": "building"})  # lifts the size limits
    by_name = {p.name: p for p in skeleton.params}
    dims = ("width_mm", "depth_mm", "height_mm")
    if not all(n in by_name and by_name[n].kind == "length" for n in dims):
        return skeleton  # the skeleton check reports the missing parameters
    # A block is the whole object, whatever box the model gave its module.
    modules = modules_with(skeleton, blocks, dims)
    houses = [m for m in blocks if m.block is not None and m.block.kind == "house"]
    env = {p.name: float(p.default) for p in skeleton.params if not isinstance(p.default, str)}
    limits = {n: (env[n] * SHRINK, env[n] * REACH) for n in dims}
    if houses:
        try:
            limits = house_limits(normalize_block(houses[0].block), env)  # type: ignore[arg-type]
        except BlockError:
            return skeleton.model_copy(update={"modules": modules})
    if any(m.block is not None and normalize_block(m.block).roof == "shed" for m in blocks):
        span = "depth_mm" if env["width_mm"] >= env["depth_mm"] else "width_mm"
        low, high = limits[span]
        limits[span] = (low, min(high, float(SHED_SPAN_MAX_MM)))
    params = []
    for p in skeleton.params:
        if p.name in limits and not isinstance(p.default, str):
            low, high = limits[p.name]
            default = float(p.default)
            low = max(p.min if p.min is not None else low, min(low, default))
            high = min(p.max if p.max is not None else high, max(high, default))
            p = p.model_copy(update={"min": min(low, default), "max": max(high, default)})
        params.append(p)
    return skeleton.model_copy(update={"params": params, "modules": modules})


def modules_with(
    skeleton: Skeleton, houses: list[ModuleBrief], dims: tuple[str, str, str]
) -> list[ModuleBrief]:
    alone = len(skeleton.modules) == 1
    return [
        m.model_copy(update={"size": dims, **({"origin": (0, 0, 0)} if alone else {})})
        if m in houses
        else m
        for m in skeleton.modules
    ]


def block_steps(kind: str, local_ids: list[str]) -> list[tuple[str, str, list[str]]]:
    """Build steps of a block module: (title, text, part ids local to the module)."""
    if kind == "house":
        return steps(local_ids)
    result = []
    for title, text, prefixes in FURNITURE_STEPS[kind]:
        ids = [i for i in local_ids if i.rstrip("0123456789") in prefixes]
        if ids:
            result.append((title, text, ids))
    return result
