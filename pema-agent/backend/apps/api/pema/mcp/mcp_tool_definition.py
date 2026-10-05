# ported from: src/mcp/mcp-tool-definition.ts
"""Turn ONE tool of an external MCP server (from ``tools/list``) into an internal ``ToolSpec`` that has both
default-deny doors every other tool in the catalogue must pass (see ``pema_contracts.tools``).

This is the SECURITY CORE of the MCP client feature: the external server is added by an operator, but what it
RETURNS is still untrusted data, exactly like a web page (the server may be compromised, or may deliberately
return instructions). Every output goes through the untrusted-content wrapper; every failing branch (raised,
timed out, permission lost mid-turn) returns a tool-failure result and never raises into the agent loop, the
repo-wide convention (``tool-failure-result.ts``).

Forced deviations (``@ai-sdk/mcp`` -> ``mcp`` SDK, sync -> async, one tenant -> clinics):

* the original injected ONE function ``kiemGan(agentId)`` (so the core needed no DB) and used it for both
  doors. Postgres is async, but the schema door (``ToolSpec.available``) is synchronous, so the function is
  split: ``is_granted(agent_id)`` answers door 1 from the in-memory binding cache; ``confirm_grant(agent_id)``
  is async, asks the DATABASE and is the door-2 re-check (it is therefore stricter than the original: a
  revocation takes effect at the next call, not at the next cache refresh);
* ``aiTool.execute`` / ``aiTool.inputSchema`` become ``call_tool(name, args)`` of the connection and the raw
  JSON schema of the tool;
* ``Promise.race`` timeout becomes ``asyncio.timeout`` and really cancels the call;
* the wrapper and the failure-result builder are parameters (``wrap`` and ``fail``), defaulting to the
  versions of package D4 (``wrap_untrusted_content`` and ``ket_qua_loi``);
* an MCP result with ``isError: true`` is returned as a FAILURE (the original wrapped its text like a success,
  which the tool loop guard then never counted); its text is untrusted, so it goes inside the wrapper;
* three extra door-2 checks that do not exist in the original and are cheap: the ``MCP_ENABLED`` kill switch
  (so turning it off blocks a tool already in a running turn), the policy profile gate (``mcp_profile_gate``;
  ``patient_channel`` is off by default) and the clinic of the turn must be the clinic of the server.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Final, cast
from uuid import UUID

from pema.agent.tools.tool_failure_result import ket_qua_loi as tool_failure_result
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tuning_settings import get_tuning_bool
from pema.mcp.mcp_profile_gate import MCP_ALLOWED_PROFILES, MCP_TOOL_KEY_PREFIX, mcp_allowed_for_profile
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolScope, ToolSpec

MAX_TOOL_KEY_LENGTH: Final = 64
"""Model APIs accept function names of ``[A-Za-z0-9_-]`` up to about 64 characters."""

_ERROR_TEXT_LIMIT: Final = 300
_NOT_GRANTED = "Tool ngoài không còn được cấp cho agent này"

type WrapFn = Callable[[str, str], str]
type FailFn = Callable[[str], object]


def mcp_tool_name(server_name: str, tool_name: str, server_id: str) -> str:
    """``tenToolMcp``: the tool name sent to the LLM; the prefix ``mcp__<server slug>__`` prevents a clash
    with an
    internal tool or a same-named tool of another MCP server.

    Normalising ``server_name`` to lower case + ``[a-z0-9_]`` can LOSE information (Vietnamese diacritics and
    special characters all become ``_``), so two servers with completely different names may normalise to the
    SAME slug. Without a hash the two servers would produce the SAME key and the tool of the later server
    would SILENTLY overwrite the earlier one in the tools mapping sent to the model: a tool disabled with no
    error anywhere, the most dangerous kind of bug because it is silent. A CLEAN name (normalisation changes
    nothing, key within the ceiling) is NOT hashed: two servers with the same CLEAN name (both called
    "Notion") is an accepted leftover in V1, an operator sees the duplicate by the name, it is not the silent
    class above.

    ``tool_name`` is chosen by the EXTERNAL server (not typed by the operator), so nothing guarantees it
    matches the function-name charset the model API accepts; a real server sending a name with spaces, unicode
    or too long would make the model request be rejected by the provider, breaking the WHOLE turn, not just
    that tool. So ``tool_name`` goes through the same normalisation and the WHOLE key is cut to 64 characters.

    On any loss (server OR tool) or a key over the ceiling, the first 8 hex characters of
    ``sha256(server_id + NUL + original tool_name)`` are appended: both are hashed because two tools of the
    SAME server with different names (two long names sharing a prefix, different tails) must still produce
    different keys after being cut to the same prefix. ``server_id`` is always UNIQUE
    (``secrets.token_hex(8)``).
    """
    lower = server_name.lower()
    slug = re.sub(r"^_+|_+\Z", "", re.sub(r"[^a-z0-9_]+", "_", lower))
    base = slug or "server"
    clean_tool = re.sub(r"^_+|_+\Z", "", re.sub(r"[^A-Za-z0-9_-]+", "_", tool_name)) or "tool"
    lossy = slug == "" or slug != lower or clean_tool != tool_name
    key = f"{MCP_TOOL_KEY_PREFIX}{base}__{clean_tool}"
    if lossy or len(key) > MAX_TOOL_KEY_LENGTH:
        digest = hashlib.sha256(f"{server_id}\u0000{tool_name}".encode("utf-8", errors="replace")).hexdigest()
        suffix = f"_{digest[:8]}"
        original_max = MAX_TOOL_KEY_LENGTH - len(suffix)
        key = (key[:original_max] if len(key) > original_max else key) + suffix
    return key


def extract_mcp_result_text(raw: object) -> str:
    """``trichVanBanKetQuaMcp``: the result of a tool call has 3 shapes depending on the server: a bare
    string,
    ``{"content": [{"type": "text", "text": ...}]}`` (the standard MCP content block), or any other JSON value
    (a server that does not follow the standard), the last one lowered to ``json.dumps`` so no data is
    dropped.

    ``None`` (the tool ran but returned nothing) is lowered to an EXPLICIT empty string: an empty result is
    valid, not a "fake error"."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        content = cast(dict[str, object], raw).get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in cast(list[object], content):
                if isinstance(block, dict):
                    entry = cast(dict[str, object], block)
                    text = entry.get("text")
                    if entry.get("type") == "text" and isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    # Last net: any value must still come out as a STRING (the original: ``JSON.stringify(raw) ?? ""``).
    try:
        return json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def is_mcp_error_result(raw: object) -> bool:
    """MCP ``CallToolResult.isError``."""
    return isinstance(raw, dict) and cast(dict[str, object], raw).get("isError") is True


async def call_with_timeout[T](fn: Callable[[], Awaitable[T]], ms: int) -> T:
    """``goiCoTimeout``: force an awaitable to finish within ``ms`` or raise. An external MCP server is not
    operated by us, so it may hang forever; without a ceiling a single tool call would keep an agent turn
    alive for ever. Unlike the original (JS cannot cancel a promise that lost the race), the losing call IS
    cancelled.

    Also reused by ``mcp_connection_pool`` to bound ``list_tools()`` during discovery: the same risk of
    hanging forever, no reason to write a second copy."""
    ceiling = asyncio.timeout(ms / 1000)
    try:
        async with ceiling:
            return await fn()
    except TimeoutError:
        if ceiling.expired():
            raise TimeoutError(f"quá {ms}ms") from None
        raise


@dataclass(frozen=True)
class McpAgentTool:
    """The built tool as handed to the model (``AgentTool``)."""

    name: str
    description: str
    parameters: JsonObject
    run: Callable[[JsonObject], Awaitable[object]]

    async def execute(self, args: JsonObject) -> object:
        return await self.run(args)


def _object_schema(schema: JsonObject) -> JsonObject:
    """Model APIs want ``type: object`` at the root; an external server may send something else."""
    if schema.get("type") == "object":
        return schema
    return {"type": "object", "properties": {}}


def _one_line(text: str) -> str:
    return " ".join(text.split())[:_ERROR_TEXT_LIMIT]


def create_mcp_tool_spec(
    *,
    clinic_id: UUID,
    server_id: str,
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: JsonObject,
    call_tool: Callable[[str, JsonObject], Awaitable[object]],
    tool_call_timeout_ms: int,
    is_granted: Callable[[str], bool],
    confirm_grant: Callable[[str], Awaitable[bool]],
    allowed_profiles: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES,
    wrap: WrapFn = wrap_untrusted_content,
    fail: FailFn = tool_failure_result,
) -> ToolSpec:
    """``taoToolDefinitionMcp``."""
    key = mcp_tool_name(server_name, tool_name, server_id)
    parameters = _object_schema(input_schema)

    def available(scope: ToolScope) -> bool:
        # Door 1 (default-deny when the schema is built): not bound -> the tool is not in the schema and the
        # model does not even know it exists.
        return is_granted(scope.agent_id)

    def build(ctx: ToolContext) -> AgentTool:
        async def execute(args: JsonObject) -> object:
            # Door 2 (fail-closed re-check): covers a revocation IN THE MIDDLE of a turn (the agent lost the
            # server after the schema was built for the running turn). Must NOT be removed.
            if not get_tuning_bool("MCP_ENABLED"):
                return fail("Tool ngoài đang bị tắt")
            if not mcp_allowed_for_profile(ctx.policy.profile.key, allowed_profiles):
                return fail("Tool ngoài không được phép dùng với hồ sơ chính sách này")
            if ctx.clinic_id != clinic_id:
                return fail(_NOT_GRANTED)
            try:
                granted = await confirm_grant(ctx.agent.id)
            except Exception:  # the database is the authority: when it cannot answer, the answer is "no"
                granted = False
            if not granted:
                return fail(_NOT_GRANTED)
            try:
                raw = await call_with_timeout(lambda: call_tool(tool_name, args), tool_call_timeout_ms)
                # The content is NOT trusted: the external server is outside our control. Empty is not an
                # error (the tool ran, there is just nothing to say), but wrapping "" returns "" UNWRAPPED, so
                # a placeholder goes in BEFORE wrapping to keep a boundary instead of silently falling into
                # the except below and turning into a "fake error".
                text = extract_mcp_result_text(raw)
                source = f"MCP {server_name}/{tool_name}"
                if is_mcp_error_result(raw):
                    return fail(
                        f'Tool ngoài "{tool_name}" báo lỗi: '
                        + wrap(_one_line(text) or "(không có nội dung)", source)
                    )
                return wrap(text or "(tool ngoài không trả nội dung)", source)
            except Exception as exc:  # never raise into the agent loop
                return fail(f'Tool ngoài "{tool_name}" lỗi: {_one_line(str(exc)) or type(exc).__name__}')

        return McpAgentTool(name=key, description=description, parameters=parameters, run=execute)

    return ToolSpec(
        key=key,
        label=f"{server_name}: {tool_name}",
        description=description,
        group=ToolGroup.ACTION,
        build=build,
        available=available,
        # The scheduler has no assign/enrich flow for MCP in an isolated turn, and an external tool is always
        # in the highest risk group: mirrors why 9 other tools are excluded from scheduled turns.
        runs_in_scheduled_turn=False,
        # Not advertised in "what can you do": the external tool list changes with the dashboard
        # configuration, boasting a tool that may lose its grant at any moment would only mislead.
        counts_as_capability=False,
    )
