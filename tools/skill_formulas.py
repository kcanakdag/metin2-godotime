"""Compile original skill arithmetic to a bounded, non-executable stack program."""

from __future__ import annotations

import ast
import math
import operator
import struct

VARIABLES = ("atk", "str", "dex", "con", "k", "lv", "iq", "mwep", "ar", "chain")
OPERATORS = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div"}


def compile_formula(text: str) -> list[dict]:
    if not isinstance(text, str) or len(text) > 512:
        raise ValueError("Skill formula exceeds source bounds")
    try:
        tree = ast.parse(text.strip() or "0", mode="eval")
    except (SyntaxError, RecursionError) as error:
        raise ValueError("Invalid skill formula syntax") from error
    result = []

    def emit(node, depth=0):
        if depth > 24 or len(result) >= 128:
            raise ValueError("Skill formula exceeds program bounds")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1_000_000:
                raise ValueError("Skill formula constant exceeds bounds")
            result.append({"op": "constant", "value": float(node.value)})
        elif isinstance(node, ast.Name) and node.id in VARIABLES:
            result.append({"op": "variable", "index": VARIABLES.index(node.id)})
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            emit(node.operand, depth + 1)
            if isinstance(node.op, ast.USub):
                result.append({"op": "neg"})
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            emit(node.left, depth + 1)
            emit(node.right, depth + 1)
            result.append({"op": OPERATORS[type(node.op)]})
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("floor", "number")
            and not node.keywords
            and len(node.args) == (1 if node.func.id == "floor" else 2)
        ):
            for argument in node.args:
                emit(argument, depth + 1)
            result.append({"op": node.func.id})
        else:
            raise ValueError("Unsupported skill formula operation")
        if len(result) > 128:
            raise ValueError("Skill formula exceeds program bounds")

    emit(tree.body)
    return result


def rank_value(text: str, power_percent: int, *, source_float_power: bool = False) -> float:
    """Constant-fold rank-only costs/clocks for identical client/server lookup tables."""
    program = compile_formula(text)
    stack = []
    for instruction in program:
        op = instruction["op"]
        if op == "constant":
            value = instruction["value"]
        elif op == "variable" and instruction["index"] == VARIABLES.index("k"):
            value = power_percent / 100
            if source_float_power:
                value = struct.unpack("f", struct.pack("f", value))[0]
        elif op in ("neg", "floor"):
            a = stack.pop()
            value = -a if op == "neg" else math.floor(a)
        elif op in ("add", "sub", "mul", "div"):
            b, a = stack.pop(), stack.pop()
            if op == "div" and b == 0:
                raise ValueError("Invalid rank-only divisor")
            value = {
                "add": operator.add,
                "sub": operator.sub,
                "mul": operator.mul,
                "div": operator.truediv,
            }[op](a, b)
        else:
            raise ValueError("Cost/clock formula must depend only on skill rank")
        if not math.isfinite(value) or abs(value) > 1_000_000_000_000:
            raise ValueError("Rank-only arithmetic exceeds bounds")
        stack.append(value)
    return stack[0]
