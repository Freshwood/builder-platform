"""Tools shared by the building blocks: part constructors, orientation and splitting of long members.

A block writes into an :class:`Out`. Geometry is described in a *wall frame* (u along the wall, v
across it, z up) and mapped to the project's x/y axes by :class:`Axes`; this way a wall, a floor or a
roof is written once and used along x and along y.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from homeworking.calc_engine.pipeline.blocks.sym import E, Num, e, value
from homeworking.construction_model.assembly import (
    Cutout,
    EndCut,
    HardwareSpec,
    JointSpec,
    PartSpec,
    Repeat,
    Shape,
)
from homeworking.construction_model.base import ParamValue

LONGEST_MM = 5000  # the longest stock length of the lumber species (catalog)
LONGEST_KVH_MM = 13000  # ... and of KVH
MAX_LOCAL_ID = 20  # module id (12) + "_" + id stays below the 40 characters of a part id


class BlockError(ValueError):
    """The block cannot be built with these options or dimensions; the text tells what to change."""


@dataclass
class Out:
    """What a block produces: parts, joints and hardware in module-local coordinates."""

    parts: list[PartSpec] = field(default_factory=list)
    joints: list[JointSpec] = field(default_factory=list)
    hardware: list[HardwareSpec] = field(default_factory=list)

    def extend(self, other: Out) -> None:
        self.parts.extend(other.parts)
        self.joints.extend(other.joints)
        self.hardware.extend(other.hardware)


@dataclass(frozen=True)
class Ctx:
    """Context of one block: default parameter values (for counts) and the wood."""

    env: Mapping[str, ParamValue]
    wood: str
    """Species key (``larch``) or the placeholder ``{wood}`` if the skeleton has a ``wood`` choice."""
    reach: float = 1.0
    shrink: float = 1.0
    """Counts that depend on a length (pieces, sheets) are sized for ``reach`` times the default
    lengths, so the dimensions can still be moved that far with the same set of parts."""

    def lumber(self, a: int, b: int) -> str:
        t, w = sorted((int(a), int(b)))
        return f"lumber_{self.wood}_{t}x{w}"

    def long_lumber(self, a: int, b: int, length_mm: float) -> tuple[str, int]:
        """Material id and longest piece for a member that should not be cut into pieces: beyond the
        usual stock length it is KVH, which comes in lengths up to 13 m."""
        if length_mm > LONGEST_MM:
            t, w = sorted((int(a), int(b)))
            return f"lumber_kvh_{t}x{w}", LONGEST_KVH_MM
        return self.lumber(a, b), LONGEST_MM

    def num(self, item: Num) -> float:
        return value(item, self.env)

    def _scaled(self, item: Num, factor: float) -> float:
        if factor == 1.0:
            return self.num(item)
        scaled = {
            k: (
                v * factor
                if isinstance(v, int | float) and not isinstance(v, bool) and k.endswith("_mm")
                else v
            )
            for k, v in self.env.items()
        }
        return value(item, scaled)

    def big(self, item: Num) -> float:
        """The value at the upper end of the parameter range (for counts, see ``reach``)."""
        return self._scaled(item, self.reach)

    def low(self, item: Num) -> float:
        """The value at the lower end of the parameter range (for "does it still fit")."""
        return self._scaled(item, self.shrink)


Orient = Literal["x", "y"]


@dataclass(frozen=True)
class Axes:
    """Maps the wall frame (u, v, z) to project axes: ``x`` = wall along x, ``y`` = along y."""

    along: Orient = "x"

    def vec(self, u: Num, v: Num, z: Num) -> tuple[float | str, float | str, float | str]:
        if self.along == "x":
            return (e(u).expr(), e(v).expr(), e(z).expr())
        return (e(v).expr(), e(u).expr(), e(z).expr())


def _pid(id: str) -> str:
    if len(id) > MAX_LOCAL_ID:
        raise BlockError(f"interner Fehler: Bauteil-ID '{id}' zu lang")
    return id


def count_for(length: float, limit: float) -> int:
    """Number of equal pieces of at most ``limit`` that cover ``length``."""
    return max(1, math.ceil(length / limit - 1e-9))


def box(
    out: Out,
    ax: Axes,
    id: str,
    name: str,
    material: str,
    at: tuple[Num, Num, Num],
    size: tuple[Num, Num, Num],
    *,
    repeat: tuple[Num, str] | None = None,
    when: str | None = None,
    shape: Shape | None = None,
    cutouts: list[Cutout] | None = None,
) -> None:
    """A box part: ``at`` and ``size`` in the wall frame (u, v, z)."""
    out.parts.append(
        PartSpec(
            id=_pid(id),
            name=name,
            material=material,
            size=ax.vec(*size),
            at=ax.vec(*at),
            repeat=None if repeat is None else Repeat(count=e(repeat[0]).expr(), var=repeat[1]),
            when=when,
            shape=shape,
            cutouts=cutouts or [],
        )
    )


def member(
    out: Out,
    ax: Axes,
    id: str,
    name: str,
    material: str,
    start: tuple[Num, Num, Num],
    end: tuple[Num, Num, Num],
    *,
    section: tuple[Num, Num] | None = None,
    facing: Literal["x", "y", "z"] | None = None,
    cuts: tuple[EndCut, EndCut] = ("square", "square"),
    repeat: tuple[Num, str] | None = None,
    when: str | None = None,
) -> None:
    """A member between two end centres; ``start``/``end`` in the wall frame."""
    out.parts.append(
        PartSpec(
            id=_pid(id),
            name=name,
            material=material,
            start=ax.vec(*start),
            end=ax.vec(*end),
            section=None if section is None else (e(section[0]).expr(), e(section[1]).expr()),
            facing=facing,
            cuts=cuts,
            repeat=None if repeat is None else Repeat(count=e(repeat[0]).expr(), var=repeat[1]),
            when=when,
        )
    )


def long_box(
    out: Out,
    ax: Axes,
    ctx: Ctx,
    id: str,
    name: str,
    material: str,
    u0: Num,
    length: Num,
    v: Num | Callable[[E], Num],
    z: Num | Callable[[E], Num],
    dv: Num,
    dz: Num,
    *,
    rows: int = 1,
    limit: int = LONGEST_MM,
    when: str | None = None,
) -> None:
    """A member along u, ``rows`` times; cut into equal pieces if it exceeds the longest stock
    length. ``v`` and ``z`` may be functions of the row index (an expression)."""
    pieces = count_for(ctx.big(length), limit)
    row = e("i") if pieces == 1 else e("i // " + str(pieces))
    place_v = v(row) if callable(v) else v
    place_z = z(row) if callable(z) else z
    count = rows * pieces
    if pieces == 1:
        box(
            out,
            ax,
            id,
            name,
            material,
            (u0, place_v, place_z),
            (length, dv, dz),
            repeat=(count, "i") if count > 1 else None,
            when=when,
        )
        return
    piece = e(length) / pieces
    box(
        out,
        ax,
        id,
        name,
        material,
        (e(u0) + piece * e(f"i % {pieces}"), place_v, place_z),
        (piece, dv, dz),
        repeat=(count, "i"),
        when=when,
    )
