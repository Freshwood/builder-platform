"""Safe evaluation of the arithmetic expressions used in assembly designs.

Only a tiny, side-effect free subset of Python syntax is accepted (numbers, names, arithmetic,
comparisons, boolean logic and a few functions). Anything else is rejected with a message that
the LLM can act on.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable, Mapping
from functools import cache

Number = float

MAX_LENGTH = 300

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_COMPARE: dict[type[ast.cmpop], Callable[[float, float], bool]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_IF_CALL = re.compile(r"\bif\s*\(")
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": lambda x, n=0: round(x, int(n)),
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "sin": lambda deg: math.sin(math.radians(deg)),
    "cos": lambda deg: math.cos(math.radians(deg)),
    "tan": lambda deg: math.tan(math.radians(deg)),
}


class ExprError(ValueError):
    pass


@cache
def _parse(source: str) -> ast.expr:
    if len(source) > MAX_LENGTH:
        raise ExprError(f"Ausdruck zu lang (max. {MAX_LENGTH} Zeichen)")
    try:
        # ``if`` is a Python keyword; accept the spreadsheet-style if(cond, a, b) anyway.
        return ast.parse(_IF_CALL.sub("_if(", source), mode="eval").body
    except SyntaxError:
        raise ExprError(f"Ungültiger Ausdruck '{source}'") from None


def evaluate(value: float | int | str, env: Mapping[str, float]) -> float:
    """Evaluate a number or expression string against ``env`` (parameter values)."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return _eval(_parse(value.strip()), env, value)


def _eval(node: ast.expr, env: Mapping[str, float], source: str) -> float:
    match node:
        case ast.Constant(value=bool() as v):
            return float(v)
        case ast.Constant(value=int() | float() as v):
            return float(v)
        case ast.Name(id="true" | "True"):
            return 1.0
        case ast.Name(id="false" | "False"):
            return 0.0
        case ast.Name(id=name):
            if name not in env:
                raise ExprError(f"Unbekannter Name '{name}' in '{source}'")
            return env[name]
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_eval(operand, env, source)
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return _eval(operand, env, source)
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return float(not _eval(operand, env, source))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY:
            a, b = _eval(left, env, source), _eval(right, env, source)
            if isinstance(op, ast.Div | ast.FloorDiv | ast.Mod) and b == 0:
                raise ExprError(f"Division durch 0 in '{source}'")
            return float(_BINARY[type(op)](a, b))
        case ast.BoolOp(op=ast.And(), values=values):
            return float(all(_eval(v, env, source) for v in values))
        case ast.BoolOp(op=ast.Or(), values=values):
            return float(any(_eval(v, env, source) for v in values))
        case ast.Compare(left=left, ops=ops, comparators=comparators):
            current = _eval(left, env, source)
            for cmp, comparator in zip(ops, comparators, strict=True):
                if type(cmp) not in _COMPARE:
                    break
                nxt = _eval(comparator, env, source)
                if not _COMPARE[type(cmp)](current, nxt):
                    return 0.0
                current = nxt
            else:
                return 1.0
        case ast.IfExp(test=test, body=body, orelse=orelse):
            return _eval(body if _eval(test, env, source) else orelse, env, source)
        case ast.Call(func=ast.Name(id="_if"), args=[cond, a, b], keywords=[]):
            return _eval(a if _eval(cond, env, source) else b, env, source)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in _FUNCTIONS:
            try:
                return float(_FUNCTIONS[name](*(_eval(a, env, source) for a in args)))
            except (TypeError, ValueError):
                raise ExprError(f"Ungültiger Aufruf von {name}() in '{source}'") from None
    raise ExprError(f"Nicht erlaubter Ausdruck in '{source}'")
