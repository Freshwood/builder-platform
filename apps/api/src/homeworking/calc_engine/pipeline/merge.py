"""Join a skeleton and its module designs into one ``AssemblyDesign`` (ADR-0010, stage 4).

Modules are designed in local coordinates: the small model never needs the global layout. The
merge moves every part by the module origin, prefixes the part ids with the module id and combines
the module condition with the part condition. Everything here is a pure rewrite of expressions;
the engine checks the result afterwards like any other design.

Engine errors that name a part are mapped back to the module that owns it, so that a repair
round only re-runs the affected module (see :func:`attribute`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from homeworking.calc_engine.engine import DesignRejectedError, Engine
from homeworking.calc_engine.pipeline.blocks import block_steps
from homeworking.construction_model.assembly import (
    AssemblyDesign,
    DesignStep,
    Expr,
    HardwareSpec,
    JointSpec,
    PartSpec,
    Vec3,
)
from homeworking.construction_model.base import Origin, ParamValue
from homeworking.construction_model.pipeline import ModuleBrief, ModuleDesign, Skeleton

MAX_ID_CHARS = 40
SKELETON = "skeleton"


@dataclass(frozen=True)
class MergeResult:
    design: AssemblyDesign | None
    errors: dict[str, list[str]] = field(default_factory=dict)  # module id (or "skeleton") -> text
    part_module: dict[str, str] = field(default_factory=dict)  # merged part id -> module id

    @property
    def ok(self) -> bool:
        return self.design is not None and not self.errors


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _is_zero(value: Expr) -> bool:
    return not isinstance(value, str) and value == 0


def shift(origin: Expr, value: Expr) -> Expr:
    """``origin + value`` as a number if both are numbers, otherwise as an expression."""
    if _is_zero(origin):
        return value
    if _is_zero(value):
        return origin
    if not isinstance(origin, str) and not isinstance(value, str):
        return origin + value
    left = origin if isinstance(origin, str) else _number(origin)
    right = value if isinstance(value, str) else _number(value)
    return f"({left}) + ({right})"


def _shift_vec(origin: Vec3, vec: Vec3) -> Vec3:
    return (shift(origin[0], vec[0]), shift(origin[1], vec[1]), shift(origin[2], vec[2]))


def both(first: Expr | None, second: Expr | None) -> Expr | None:
    """Condition that holds only if both hold; ``None`` means unconditional."""
    if first is None:
        return second
    if second is None:
        return first
    left = first if isinstance(first, str) else _number(first)
    right = second if isinstance(second, str) else _number(second)
    return f"({left}) and ({right})"


def _prefixed(module: str, local: str) -> str:
    return f"{module}_{local}"


def _part(module: ModuleBrief, part: PartSpec) -> PartSpec:
    update: dict[str, object] = {
        "id": _prefixed(module.id, part.id),
        "when": both(module.when, part.when),
    }
    if part.at is not None:
        update["at"] = _shift_vec(module.origin, part.at)
    if part.start is not None and part.end is not None:
        update["start"] = _shift_vec(module.origin, part.start)
        update["end"] = _shift_vec(module.origin, part.end)
    return part.model_copy(update=update)


def _joint(module: str, joint: JointSpec) -> JointSpec:
    return joint.model_copy(
        update={"part": _prefixed(module, joint.part), "into": _prefixed(module, joint.into)}
    )


def _hardware(module: ModuleBrief, item: HardwareSpec) -> HardwareSpec:
    return item.model_copy(update={"when": both(module.when, item.when)})


def merge(skeleton: Skeleton, modules: Iterable[ModuleDesign]) -> MergeResult:
    """Merge the module designs into one design. Structural problems are returned per module."""
    delivered: dict[str, ModuleDesign] = {}
    errors: dict[str, list[str]] = {}

    def fail(key: str, message: str) -> None:
        errors.setdefault(key, []).append(message)

    briefs = {m.id: m for m in skeleton.modules}
    if len(briefs) != len(skeleton.modules):
        fail(SKELETON, "Modul-IDs im Gerüst sind nicht eindeutig")
    for design in modules:
        if design.module not in briefs:
            fail(design.module, f"Modul '{design.module}' steht nicht im Gerüst")
        elif design.module in delivered:
            fail(design.module, f"Modul '{design.module}' wurde doppelt geliefert")
        else:
            delivered[design.module] = design
    for module_id in briefs:
        if module_id not in delivered:
            fail(module_id, f"Modul '{module_id}' fehlt")

    parts: list[PartSpec] = []
    joints: list[JointSpec] = []
    hardware: list[HardwareSpec] = []
    part_module: dict[str, str] = {}
    for module_id, brief in briefs.items():
        module_design = delivered.get(module_id)
        if module_design is None:
            continue
        local_ids = [p.id for p in module_design.parts]
        for duplicate in sorted({i for i in local_ids if local_ids.count(i) > 1}):
            fail(module_id, f"Bauteil-ID '{duplicate}' kommt im Modul mehrfach vor")
        for part in module_design.parts:
            merged = _part(brief, part)
            if len(merged.id) > MAX_ID_CHARS:
                fail(module_id, f"Bauteil-ID '{part.id}' ist zu lang (Modul-ID + ID ≤ 39 Zeichen)")
                continue
            part_module[merged.id] = module_id
            parts.append(merged)
        known = set(local_ids)
        for joint in module_design.joints:
            unknown = sorted({joint.part, joint.into} - known)
            if unknown:
                fail(module_id, f"joints nennen unbekannte Bauteil-IDs: {', '.join(unknown)}")
            else:
                joints.append(_joint(module_id, joint))
        hardware.extend(_hardware(brief, item) for item in module_design.hardware)

    if errors or not parts:
        return MergeResult(None, errors, part_module)
    try:
        merged_design = AssemblyDesign(
            object_type=skeleton.object_type,
            summary=skeleton.summary,
            category=skeleton.category,
            use=skeleton.use,
            support=skeleton.support,
            origin=Origin.AI,
            params=skeleton.params,
            parts=parts,
            joints=joints,
            hardware=hardware,
            finish=skeleton.finish,
            variants=skeleton.variants,
        )
    except ValidationError as exc:
        for problem in exc.errors():
            fail(SKELETON, str(problem["msg"]).removeprefix("Value error, "))
        return MergeResult(None, errors, part_module)
    return MergeResult(merged_design, {}, part_module)


def attribute(errors: Iterable[str], part_module: Mapping[str, str]) -> dict[str, list[str]]:
    """Assign engine errors to the module whose part they name; the rest belongs to the skeleton
    (parameters, overall shape, support) and is repaired there."""
    patterns = {
        part_id: re.compile(rf"(?<![a-z0-9_]){re.escape(part_id)}(?![a-z0-9_])")
        for part_id in part_module
    }
    result: dict[str, list[str]] = {}
    for message in errors:
        owners = {
            module
            for pid, rx in patterns.items()
            if rx.search(message)
            for module in [part_module[pid]]
        }
        for owner in sorted(owners) or [SKELETON]:
            result.setdefault(owner, []).append(message)
    return result


def check(
    engine: Engine, result: MergeResult, params: Mapping[str, ParamValue] | None = None
) -> MergeResult:
    """Run the engine over a merged design and attribute its rejection to modules."""
    if result.design is None:
        return result
    try:
        engine.validate_design(result.design, params or {})
    except DesignRejectedError as exc:
        return MergeResult(
            result.design, attribute(exc.errors, result.part_module), result.part_module
        )
    return result


def localize(errors: Iterable[str], module: str, part_module: Mapping[str, str]) -> list[str]:
    """Rewrite merged part ids in engine messages back to the module's own ids, so that a module
    repair sees the ids it wrote."""
    prefix = f"{module}_"
    own = sorted((p for p, owner in part_module.items() if owner == module), key=len, reverse=True)
    if not own:
        return list(errors)
    rx = re.compile(r"(?<![a-z0-9_])(" + "|".join(re.escape(p) for p in own) + r")(?![a-z0-9_])")
    return [rx.sub(lambda m: m.group(1).removeprefix(prefix), message) for message in errors]


def module_steps(
    skeleton: Skeleton,
    design: AssemblyDesign,
    part_module: Mapping[str, str],
    texts: Mapping[str, tuple[str, str]] | None = None,
) -> list[DesignStep]:
    """One build step per module, in skeleton order, mounting exactly the module's parts.

    ``texts`` maps a module id to (title, text) as the documentation stage worded it; modules
    without wording get their title and role, so the result never depends on a model."""
    steps: list[DesignStep] = []
    for brief in skeleton.modules:
        ids = [p.id for p in design.parts if part_module.get(p.id) == brief.id]
        if not ids:
            continue
        if brief.block is not None:
            # Engine-built modules have their own fixed steps (foundation, walls, roof).
            prefix = f"{brief.id}_"
            for title, text, local in block_steps(
                brief.block.kind, [i.removeprefix(prefix) for i in ids]
            ):
                steps.append(
                    DesignStep(title=title, text=text, parts=[f"{prefix}{i}" for i in local])
                )
            continue
        title, text = (texts or {}).get(brief.id) or (brief.title, brief.role)
        steps.append(DesignStep(title=title[:80], text=text[:800], parts=ids))
    return steps
