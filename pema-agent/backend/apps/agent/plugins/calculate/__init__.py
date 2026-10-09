"""The ``calculate`` plugin: +, -, *, /, //, %, ** and parentheses on numbers, nothing else.

The expression is parsed with ``ast`` and walked by hand; names, calls, attributes and every other node are
refused, and powers and results are kept small, so no input can run code or exhaust the process.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Final

from pydantic import BaseModel, Field

from agent_app.plugins import PluginContext
from agentcore import PromptEnv, SessionSection, ToolContext, ToolOutput, ToolSpec
from agentcore.prompt.data import SessionData

TOOL: Final = "calculate"
MAX_EXPRESSION_CHARS: Final = 200
MAX_DIGITS: Final = 100
"""Whole results (and intermediate ones) of more digits than this are refused."""
MAX_PRECISION: Final = 15

Number = int | float

BINARY: Final[dict[type[ast.operator], Callable[[Number, Number], Number]]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: operator.mod,
}
UNARY: Final[dict[type[ast.unaryop], Callable[[Number], Number]]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
GUIDANCE: Final = (
    f"## Arithmetic\nFor any arithmetic beyond the trivial, call `{TOOL}` with the expression and give its "
    "result; do not work sums out yourself."
)


class CalculationError(ValueError):
    pass


class CalculateArgs(BaseModel):
    expression: str = Field(
        min_length=1,
        max_length=MAX_EXPRESSION_CHARS,
        description="Arithmetic on numbers, e.g. (120000 * 3 - 15000) / 2. Allowed: + - * / // % ** ( ).",
    )


def evaluate(expression: str) -> Number:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError) as err:
        raise CalculationError("not an arithmetic expression") from err
    return _check(_eval(tree.body))


def format_number(value: Number, precision: int) -> str:
    if isinstance(value, int):
        return str(value)
    rounded = round(value, precision)
    if rounded.is_integer() and abs(rounded) < 10**15:
        return str(int(rounded))
    return repr(rounded)


def _eval(node: ast.expr) -> Number:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise CalculationError("only numbers are allowed")
        return _check(value)
    if isinstance(node, ast.UnaryOp):
        unary = UNARY.get(type(node.op))
        if unary is None:
            raise CalculationError("only + and - may stand before a number")
        return unary(_eval(node.operand))
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            return _check(_power(left, right))
        binary = BINARY.get(type(node.op))
        if binary is None:
            raise CalculationError("allowed operators: + - * / // % **")
        try:
            return _check(binary(left, right))
        except ZeroDivisionError as err:
            raise CalculationError("division by zero") from err
    raise CalculationError("only numbers, + - * / // % ** and parentheses are allowed")


def _power(base: Number, exponent: Number) -> Number:
    if base == 0 and exponent < 0:
        raise CalculationError("division by zero")
    if abs(base) > 1 and exponent > 0 and exponent * math.log10(abs(base)) > MAX_DIGITS:
        raise CalculationError(f"the result has more than {MAX_DIGITS} digits")
    try:
        result: Number | complex = base**exponent
    except OverflowError as err:
        raise CalculationError("the result is too large") from err
    if isinstance(result, complex):
        raise CalculationError("the result is not a real number")
    return result


def _check(value: Number) -> Number:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalculationError("the result is too large")
        return value
    if value != 0 and math.log10(abs(value)) >= MAX_DIGITS:
        raise CalculationError(f"the result has more than {MAX_DIGITS} digits")
    return value


def register(ctx: PluginContext) -> None:
    precision = ctx.config.get("precision", 10)
    if isinstance(precision, bool) or not isinstance(precision, int) or not 0 <= precision <= MAX_PRECISION:
        raise ValueError(f"precision must be a whole number from 0 to {MAX_PRECISION}")

    async def calculate(args: CalculateArgs, _ctx: ToolContext) -> ToolOutput:
        try:
            value = evaluate(args.expression)
        except CalculationError as err:
            return ToolOutput(text=f"cannot calculate: {err}", is_error=True)
        return ToolOutput(text=format_number(value, precision))

    def guidance(env: PromptEnv, _data: SessionData) -> str | None:
        return GUIDANCE if TOOL in env.tool_names else None

    ctx.register_tool(
        ToolSpec(
            name=TOOL,
            description="Evaluate an arithmetic expression exactly and return the number.",
            args_model=CalculateArgs,
            handler=calculate,
            timeout_s=5.0,
            read_only=True,
        )
    )
    ctx.register_prompt_section(SessionSection("calculate", guidance))
