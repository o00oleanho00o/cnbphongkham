# ported from: src/agent/tools/tool-schema-provider-compat.test.ts (the shape rules, applied to FunctionTool)
"""Tests of ``FunctionTool`` and ``json_schema_of`` (no zalo-agent test; the rules come from the provider-compat
test and the zod/pydantic gap)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool, json_schema_of
from pema.agent.tools.tool_failure_result import la_ket_qua_loi


class _Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(description="nhãn")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["a", "b"] = Field(description="chọn một")
    text: Annotated[str, Field(min_length=1, max_length=10, description="chữ")]
    index: int | None = Field(default=None, ge=1, description="số thứ tự")
    inner: _Inner | None = Field(default=None, description="lồng nhau")
    flag: bool | None = Field(default=None, description="cờ")


def test_json_schema_of_root_is_an_object_without_refs_titles_or_null_branches() -> None:
    """GỐC phải là object, không $ref/title/anyOf-null (hình dạng zod cho ra)"""
    schema = json_schema_of(_Args)
    assert schema["type"] == "object"
    assert schema["required"] == ["mode", "text"]
    text = str(schema)
    assert "$ref" not in text
    assert "'title'" not in text
    assert "'null'" not in text
    assert schema["properties"]["index"] == {"type": "integer", "minimum": 1, "description": "số thứ tự"}
    assert schema["properties"]["inner"]["properties"]["label"]["description"] == "nhãn"
    assert schema["additionalProperties"] is False


async def test_execute_validates_and_passes_the_parsed_model_to_the_handler() -> None:
    """execute kiểm tham số rồi mới gọi handler; số dạng chuỗi được ép kiểu như z.coerce"""
    seen: list[_Args] = []

    async def handler(args: _Args) -> object:
        seen.append(args)
        return "ok"

    tool = FunctionTool(name="demo", description="d", input_model=_Args, handler=handler)
    result = await tool.execute({"mode": "a", "text": "xin", "index": "3"})
    assert result == "ok"
    assert seen[0].index == 3


async def test_execute_invalid_arguments_is_a_marked_failure_never_an_exception() -> None:
    """tham số sai là nhánh hỏng có đánh dấu, không ném ra agent loop, và không lộ giá trị đã gõ"""

    async def handler(args: _Args) -> object:
        raise AssertionError("handler must not run")

    tool = FunctionTool(name="demo", description="d", input_model=_Args, handler=handler)
    result = await tool.execute({"mode": "z", "text": "SECRET-VALUE-0123456789"})
    assert la_ket_qua_loi(result)
    assert "SECRET-VALUE" not in result["loi"]
    assert "mode" in result["loi"]
