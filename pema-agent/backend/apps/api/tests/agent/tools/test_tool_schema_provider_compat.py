# ported from: src/agent/tools/tool-schema-provider-compat.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The schema of a tool does NOT stay in-house: it flies straight to the LLM provider on EVERY turn. A provider that
looks harder at the schema makes a structure that is valid for the schema library still choke the whole request,
and since the tool set travels with every turn the bot goes COMPLETELY mute, not just on the turns that use that
tool.

Paid for in production 06/08/2026: ``z.tuple()`` in ``create_excel_file`` translated into JSON Schema draft-07 with
``items`` as an ARRAY. Google's OpenAI-compatible layer only takes 2020-12 (where ``items`` must be an object or a
boolean) so it answered 400 to every message. 9router and Anthropic both swallow the old shape, so the error sat
quietly until the provider was changed: exactly the kind of trap a test must catch instead of waiting for a user.

This test scans the STRUCTURE, not one tool: whoever adds a tuple to a new tool turns it red on the spot.

Forced deviation: the original read ``asSchema(tool.inputSchema).jsonSchema`` (what the AI SDK sends); here it is
``AgentTool.parameters`` (what the hand-written loop sends as ``tools[].function.parameters``). A tuple is
``prefixItems`` (2020-12) in pydantic, which is also scanned.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import pytest

from pema.agent.tools.testing import FakeKbAvailability, make_tool_context, make_tool_deps
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.config.runtime_image_settings import ImageSettingsUpdate, update_image_settings
from pema.config.runtime_settings_kv import reset_runtime_settings_kv
from pema_contracts.common import JsonObject


def _every_node(node: object, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every node of the JSON Schema tree, with a path so the error message points at the exact place."""
    if isinstance(node, list):
        for i, child in enumerate(cast("list[object]", node)):
            yield from _every_node(child, f"{path}[{i}]")
        return
    if not isinstance(node, dict):
        return
    obj: dict[str, Any] = node  # pyright: ignore[reportUnknownVariableType]
    yield path, obj
    for key, child in obj.items():
        yield from _every_node(child, f"{path}.{key}")


@pytest.fixture(autouse=True)
def _cipher_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "00" * 32)


@pytest.fixture
async def schemas() -> AsyncIterator[list[tuple[str, JsonObject]]]:
    """Switch on the infrastructure of the 3 tools that have a gate, so the scan sees ALL the tools and does not
    silently skip exactly the tool that is broken."""
    reset_runtime_settings_kv()
    await update_image_settings(ImageSettingsUpdate(base_url="https://router.test", model="m", api_key="k"))
    kb = FakeKbAvailability({"agent-test"})
    registry = DefaultToolRegistry(make_tool_deps(kb_availability=kb, sidecar_configured=lambda: True))
    tools = await registry.build_agent_tools(make_tool_context())
    yield [(name, tool.parameters) for name, tool in tools.items()]
    reset_runtime_settings_kv()


def _by_name(schemas: list[tuple[str, JsonObject]], name: str) -> JsonObject:
    return next(schema for tool_name, schema in schemas if tool_name == name)


def test_tool_schema_scan_covers_the_whole_tool_set_not_an_empty_array_read_as_a_pass(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """quét được đủ bộ tool, không phải mảng rỗng đọc ra như đã đạt"""
    assert len(schemas) >= 14, f"chỉ dựng được {len(schemas)} tool - bộ quét đang nhìn hụt"


def test_tool_schema_root_of_every_tool_must_be_type_object_or_deepseek_refuses_the_whole_request(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """GỐC của mọi tool phải là `type: "object"` - thiếu là DeepSeek chối cả request

    The ROOT is where providers look first, and the only place a union is NOT allowed: zod translated a root
    ``z.union`` / ``z.discriminatedUnion`` into ``{"$schema":..., "oneOf":[...]}`` with no ``type`` key. Paid for
    07/08/2026: ``schedule_task`` used a root ``discriminatedUnion`` and DeepSeek answered 400 "schema must be a JSON
    Schema of 'type: object', got 'type: null'" to EVERY message. A union NESTED inside an object is valid everywhere.
    """
    pham = [
        f"{name}: type={schema.get('type')!r}, khóa gốc=[{','.join(schema)}]"
        for name, schema in schemas
        if schema.get("type") != "object"
    ]
    assert pham == [], (
        "Giữ union làm hợp đồng nội bộ, còn schema đưa ra một object phẳng rồi parse lại trong handler "
        "(mẫu ở schedule_task_tool.py):\n  " + "\n  ".join(pham)
    )


def test_tool_schema_no_tool_has_items_as_an_array_or_prefix_items_a_tuple_google_refuses(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """KHÔNG tool nào có `items` dạng mảng (tuple draft-07) - Google chối cả request"""
    pham: list[str] = []
    for name, schema in schemas:
        for path, node in _every_node(schema, name):
            if isinstance(node.get("items"), list):
                pham.append(f"{path}.items")
            if "prefixItems" in node:
                pham.append(f"{path}.prefixItems")
    assert pham == [], (
        "Chỗ này dịch từ tuple. Đổi sang list[x] có độ dài cố định - ràng buộc lúc chạy y hệt mà JSON Schema thì "
        "mọi nhà cung cấp đều nhận:\n  " + "\n  ".join(pham)
    )


def test_tool_schema_every_const_and_enum_must_be_a_string_google_builds_enum_from_them(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """MỌI `const` và `enum` phải là chuỗi - Google dựng enum từ chúng và chỉ nhận chuỗi

    ``Schema.enum`` in Google's API is ``repeated string``. It must check ``const`` too and not only ``enum``: a
    union of numeric literals becomes ``anyOf: [{type:"number",const:1}...]``, NOT an ``enum``, and Google's own
    provider folds ``const`` into ``enum: [1]``. A rule that only looks at ``enum`` would stay GREEN even while the
    real error sits there.
    """
    pham: list[str] = []
    for name, schema in schemas:
        for path, node in _every_node(schema, name):
            if "const" in node and not isinstance(node["const"], str):
                pham.append(f"{path}.const = {node['const']!r}")
            values = node.get("enum")
            if not isinstance(values, list):
                continue
            for i, value in enumerate(values):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                if not isinstance(value, str):
                    pham.append(f"{path}.enum[{i}] = {value!r}")
    assert pham == [], (
        "Chỗ này thường dịch từ union literal SỐ. Đổi sang khoảng số (int với ge/le) - không sinh const/enum mà "
        "ràng buộc vẫn tương đương:\n  " + "\n  ".join(pham)
    )


def test_tool_schema_the_scanner_reaches_the_deepest_place_it_does_not_stop_at_the_surface(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """bộ quét ĐI TỚI được chỗ sâu nhất, không dừng ở tầng mặt

    The multiply formula cell sits at sheets[].rows[][].anyOf[n]: the very place that broke. Without this assertion a
    scanner that only looks at level one would still be green.
    """
    excel = _by_name(schemas, "create_excel_file")
    co_cot_nhan = any(node.get("pattern") == "^[A-Za-z]{1,2}$" for _p, node in _every_node(excel, "root"))
    assert co_cot_nhan, "bộ quét không chạm tới schema chữ cái cột - nó đang bỏ sót nhánh sâu"


def test_tool_schema_the_scanner_sees_both_const_and_enum_nodes_or_the_other_rule_is_empty(
    schemas: list[tuple[str, JsonObject]],
) -> None:
    """bộ quét THẤY được cả nút `const` lẫn nút `enum` - không thì luật kia đúng rỗng

    The rule "const/enum must be a string" is green even when the scanner finds no node. This assertion tells
    "no violation" from "sees nothing".
    """
    nodes = [node for name, schema in schemas for _p, node in _every_node(schema, name)]
    so_const = sum(1 for node in nodes if "const" in node)
    so_enum = sum(1 for node in nodes if isinstance(node.get("enum"), list))
    assert so_const > 0, "không thấy nút const nào trong cả bộ tool - bộ quét đang mù"
    assert so_enum > 0, "không thấy nút enum nào trong cả bộ tool - bộ quét đang mù"
