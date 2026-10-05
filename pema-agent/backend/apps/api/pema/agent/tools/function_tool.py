# ported from: src/agent/tools/tool-catalog-types.ts (the tool() factory of the Vercel AI SDK)
"""``FunctionTool``: the replacement of ``tool()`` from the Vercel AI SDK, implementing ``AgentTool``.

Forced deviation (Vercel AI SDK -> hand-written loop on the ``openai`` SDK): the SDK took a zod
``inputSchema``, turned it into JSON Schema for the provider, and VALIDATED the model's arguments before
calling ``execute``. Here the schema is a pydantic model; ``parameters`` is its JSON Schema
(post-processed so it keeps the exact shape zod produced, see ``json_schema_of``) and ``execute``
validates the raw arguments first. A failed validation is NOT an exception: it is a marked tool failure
(``ket_qua_loi``) so the loop can count it, the same contract as every other failing branch
(tool-failure-result.ts).

The error text lists only field locations and the validator message, never the offending VALUE (it may be
personal data a stranger typed).

Schema shape rules, kept from ``tool-schema-provider-compat.test.ts`` (paid for in production on
2026-08-06 and 2026-08-07: a provider that is strict about the schema rejects EVERY request, because the
tool set travels with every turn):

* the ROOT is always ``{"type": "object"}`` (no union at the root: DeepSeek refuses it);
* no tuple (``prefixItems`` / ``items`` as an array): Google's OpenAI-compatible layer only takes 2020-12
  object ``items``;
* every ``const`` / ``enum`` is a string: Google builds ``Schema.enum`` from them and only takes strings.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema_contracts.common import JsonObject

type _Node = dict[str, Any]

_SCHEMA_KEYS_WITH_NODE = ("items", "additionalProperties", "not", "if", "then", "else")
_SCHEMA_KEYS_WITH_LIST = ("anyOf", "oneOf", "allOf")
_SCHEMA_KEYS_WITH_MAP = ("properties", "$defs", "patternProperties")


def _is_null_branch(branch: object) -> bool:
    return isinstance(branch, dict) and cast("_Node", branch).get("type") == "null"


def _drop_null_branch(node: _Node) -> _Node:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list):
        return node
    all_branches = cast("list[object]", any_of)
    kept = [b for b in all_branches if not _is_null_branch(b)]
    if len(kept) == len(all_branches):
        return node
    if len(kept) == 1 and isinstance(kept[0], dict):
        rest = {k: v for k, v in node.items() if k != "anyOf"}
        return {**cast("_Node", kept[0]), **rest}
    return {**node, "anyOf": kept}


def _resolve(node: _Node, defs: dict[str, _Node], depth: int = 0) -> _Node:
    """Inline ``$ref`` (no provider needs the indirection, and some refuse it) and clean the node."""
    if depth > 32:
        raise ValueError("schema nests too deep or is recursive")
    ref = node.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        target = defs.get(name)
        if target is None:
            raise ValueError(f"unknown schema reference {name!r}")
        merged: _Node = {**_resolve(target, defs, depth + 1)}
        merged.update({k: v for k, v in node.items() if k != "$ref"})
        return merged

    out: _Node = {k: v for k, v in node.items() if k not in ("title", "$defs")}

    for key in _SCHEMA_KEYS_WITH_NODE:
        value = out.get(key)
        if isinstance(value, dict):
            out[key] = _resolve(cast("_Node", value), defs, depth + 1)
    for key in _SCHEMA_KEYS_WITH_MAP:
        value = out.get(key)
        if isinstance(value, dict):
            children = cast("dict[str, Any]", value)
            out[key] = {
                name: _resolve(cast("_Node", child), defs, depth + 1) if isinstance(child, dict) else child
                for name, child in children.items()
            }
    for key in _SCHEMA_KEYS_WITH_LIST:
        value = out.get(key)
        if isinstance(value, list):
            items = cast("list[Any]", value)
            out[key] = [
                _resolve(cast("_Node", child), defs, depth + 1) if isinstance(child, dict) else child
                for child in items
            ]

    # ``Optional[X]`` is ``anyOf: [X, {type: null}]`` in pydantic but just ``X`` (not required) in zod:
    # drop the null branch, and a single remaining branch replaces the node.
    out = _drop_null_branch(out)
    if "default" in out and out["default"] is None:
        del out["default"]
    return out


def json_schema_of(model: type[BaseModel]) -> JsonObject:
    """JSON Schema of an input model, in the shape the providers accept (see the module docstring)."""
    raw: _Node = model.model_json_schema(mode="validation")
    defs = cast("dict[str, _Node]", raw.get("$defs", {}))
    schema = _resolve(raw, defs)
    schema["type"] = "object"
    schema.setdefault("properties", {})
    return schema


def _describe_validation_error(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors(include_input=False, include_url=False)[:5]:
        where = ".".join(str(p) for p in item["loc"]) or "(gốc)"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


class NoArgs(BaseModel):
    """``z.object({})``: a tool with no parameter (``get_datetime``, ``get_group_info``)."""

    model_config = ConfigDict(extra="forbid")


class FunctionTool[ArgsT: BaseModel]:
    """A built tool. ``handler`` receives the VALIDATED model and returns a bare string (success) or a
    ``ket_qua_loi`` (failure); it never raises for an expected failure."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_model: type[ArgsT],
        handler: Callable[[ArgsT], Awaitable[object]],
        parameters: JsonObject | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._input_model = input_model
        self._handler = handler
        self._parameters: JsonObject | None = parameters
        """Advertised JSON Schema when the pydantic model cannot express it (nested document blocks)."""

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def input_model(self) -> type[ArgsT]:
        return self._input_model

    @property
    def parameters(self) -> JsonObject:
        if self._parameters is None:
            self._parameters = json_schema_of(self._input_model)
        return self._parameters

    async def execute(self, args: JsonObject) -> object:
        try:
            parsed = self._input_model.model_validate(args)
        except ValidationError as err:
            return ket_qua_loi(
                f"Tham số gọi tool {self._name} không hợp lệ ({_describe_validation_error(err)}). "
                "Gọi lại với tham số đúng."
            )
        return await self._handler(parsed)
