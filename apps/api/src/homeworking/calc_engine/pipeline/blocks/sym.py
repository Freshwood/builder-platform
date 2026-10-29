"""Small symbolic layer for the building blocks: arithmetic on numbers and parameter expressions.

A block computes its geometry once, at the default parameter values, to decide counts and
layout (how many studs, which segments), but it writes every *dimension* as an expression over the
design parameters. That keeps a generated module parametric: when the customer moves a slider the
engine re-evaluates the same expressions, like for a module the model wrote by hand.

``E`` renders to the engine's expression language (``calc_engine.assembly.expr``). Constants are
folded, so a block that only uses numbers yields plain numbers.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping

from homeworking.calc_engine.assembly.expr import evaluate_number
from homeworking.construction_model.assembly import Expr
from homeworking.construction_model.base import ParamValue

_ATOM = re.compile(r"^(?:[0-9]+(?:\.[0-9]+)?|[a-z_][a-z0-9_]*)$")


def _fmt(value: float) -> str:
    rounded = round(value, 3)
    return str(int(rounded)) if float(rounded).is_integer() else repr(rounded)


class E:
    """An expression: a constant or text over parameters. Immutable."""

    __slots__ = ("atomic", "const", "text")

    def __init__(self, text: str, const: float | None = None, *, atomic: bool = False) -> None:
        self.text = text
        self.const = const
        # An atom (number, name, call, parenthesised group) needs no brackets as an operand.
        self.atomic = atomic or bool(_ATOM.match(text))

    # --- construction ------------------------------------------------------------------------

    @staticmethod
    def of(value: E | float | int | str) -> E:
        if isinstance(value, E):
            return value
        if isinstance(value, str):
            text = value.strip()
            return E(text) if _ATOM.match(text) else E(f"({text})", atomic=True)
        return E(_fmt(value), float(value))

    # --- rendering ---------------------------------------------------------------------------

    def expr(self) -> Expr:
        """Number if constant, else text: what a ``PartSpec`` field takes."""
        return round(self.const, 1) if self.const is not None else self.text

    def __str__(self) -> str:
        return self.text

    def _wrapped(self) -> str:
        return self.text if self.atomic else f"({self.text})"

    # --- arithmetic --------------------------------------------------------------------------

    def _bin(self, op: str, other: E | float | int | str, fn: object, *, swap: bool = False) -> E:
        a, b = (E.of(other), self) if swap else (self, E.of(other))
        if a.const is not None and b.const is not None:
            return E.of(fn(a.const, b.const))  # type: ignore[operator]
        return E(f"{a._wrapped()} {op} {b._wrapped()}")

    def __add__(self, other: E | float | int | str) -> E:
        if isinstance(other, int | float) and other == 0:
            return self
        return self._bin("+", other, lambda a, b: a + b)

    def __radd__(self, other: E | float | int | str) -> E:
        return self.__add__(other)

    def __sub__(self, other: E | float | int | str) -> E:
        if isinstance(other, int | float) and other == 0:
            return self
        return self._bin("-", other, lambda a, b: a - b)

    def __rsub__(self, other: E | float | int | str) -> E:
        return self._bin("-", other, lambda a, b: a - b, swap=True)

    def __mul__(self, other: E | float | int | str) -> E:
        if isinstance(other, int | float):
            if other == 1:
                return self
            if other == 0:
                return E.of(0)
        return self._bin("*", other, lambda a, b: a * b)

    def __rmul__(self, other: E | float | int | str) -> E:
        return self.__mul__(other)

    def __truediv__(self, other: E | float | int | str) -> E:
        if isinstance(other, int | float) and other == 1:
            return self
        return self._bin("/", other, lambda a, b: a / b)

    def __rtruediv__(self, other: E | float | int | str) -> E:
        return self._bin("/", other, lambda a, b: a / b, swap=True)

    def __neg__(self) -> E:
        return E.of(0) - self

    def __repr__(self) -> str:
        return f"E({self.text})"


Num = E | float | int | str


def e(value: Num) -> E:
    return E.of(value)


def call(name: str, *args: Num) -> E:
    """A call of an engine function (``sqrt``, ``max``, ``min``, ``floor``, ``ceil``)."""
    items = [E.of(a) for a in args]
    if all(i.const is not None for i in items):
        fns: dict[str, Callable[..., float]] = {
            "sqrt": math.sqrt,
            "max": max,
            "min": min,
            "floor": math.floor,
            "ceil": math.ceil,
            "abs": abs,
        }
        return E.of(fns[name](*[i.const for i in items if i.const is not None]))
    return E(f"{name}({', '.join(i.text for i in items)})", atomic=True)


def value(item: Num, env: Mapping[str, ParamValue]) -> float:
    """Numeric value at the given parameter values (the defaults)."""
    expr = E.of(item)
    if expr.const is not None:
        return expr.const
    return evaluate_number(expr.text, env)


# The repeat index of a part that is written once and repeated.
I = E("i")  # noqa: E741
