"""Tool spec rules, the registry and the built-in ``get_datetime``."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from agentcore import ToolContext, ToolOutput, ToolRegistry, ToolSpec
from agentcore.harness.tools.builtin import builtin_tools
from agentcore.harness.tools.builtin.get_datetime import GetDatetimeArgs, make_get_datetime_tool

CTX = ToolContext(session_id="s1")


class EchoArgs(BaseModel):
    text: str


async def _echo(args: EchoArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text=args.text)


def _spec(name: str = "echo") -> ToolSpec[EchoArgs]:
    return ToolSpec(name=name, description="Echo the text.", args_model=EchoArgs, handler=_echo)


def test_the_schema_comes_from_the_arguments_model() -> None:
    schema = _spec().schema()

    assert schema.name == "echo"
    assert schema.parameters["required"] == ["text"]
    assert schema.parameters["properties"]["text"]["type"] == "string"


@pytest.mark.parametrize("name", ["", "has space", "x" * 65, "dấu"])
def test_a_tool_name_providers_reject_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="Invalid tool name"):
        _spec(name)


def test_a_tool_name_is_registered_once() -> None:
    registry = ToolRegistry([_spec()])

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec())


def test_a_subset_keeps_the_requested_order_and_refuses_unknown_names() -> None:
    registry = ToolRegistry([_spec("a"), _spec("b"), _spec("c")])

    assert registry.subset(["c", "a"]).names() == ["c", "a"]
    assert registry.get("missing") is None
    with pytest.raises(ValueError, match="Unknown tool"):
        registry.subset(["a", "missing"])


FIXED_UTC = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)


async def test_get_datetime_uses_the_default_time_zone() -> None:
    tool = make_get_datetime_tool(default_timezone="Asia/Ho_Chi_Minh", clock=lambda: FIXED_UTC)

    output = await tool.handler(GetDatetimeArgs(), CTX)

    assert output == ToolOutput(text="2026-10-08T14:00:00+07:00 (Thursday, Asia/Ho_Chi_Minh)")


async def test_get_datetime_accepts_another_time_zone() -> None:
    tool = make_get_datetime_tool(default_timezone="Asia/Ho_Chi_Minh", clock=lambda: FIXED_UTC)

    output = await tool.handler(GetDatetimeArgs(timezone="UTC"), CTX)

    assert output.text == "2026-10-08T07:00:00+00:00 (Thursday, UTC)"


async def test_get_datetime_reports_an_unknown_time_zone_as_a_tool_error() -> None:
    tool = make_get_datetime_tool(clock=lambda: FIXED_UTC)

    output = await tool.handler(GetDatetimeArgs(timezone="Mars/Olympus"), CTX)

    assert output.is_error
    assert "Unknown time zone" in output.text


def test_a_wrong_default_time_zone_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="Unknown time zone"):
        builtin_tools(timezone="Not/AZone")
