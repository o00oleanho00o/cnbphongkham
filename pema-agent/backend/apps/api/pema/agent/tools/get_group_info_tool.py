# ported from: src/agent/tools/get-group-info-tool.ts
"""``get_group_info``: name, member count and member ids of the current group.

Forced deviation: ``api.getGroupInfo(threadId)`` of zca-js becomes
``GroupChannel.get_group_info(thread_id)`` returning the raw JSON object of the channel; the parsing of
the zca-js shape (``gridInfoMap``, ``memVerList``) is kept as it was, on that object."""

from __future__ import annotations

from typing import Any, cast

from pema.agent.tools.function_tool import FunctionTool, NoArgs
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.tool_send import require_channel
from pema_contracts.channel import GroupChannel
from pema_contracts.tools import ToolContext

DESCRIPTION = (
    "Lấy thông tin nhóm hiện tại: tên nhóm, số thành viên, danh sách thành viên (id + tên). "
    "Dùng trước khi tag ai đó nếu chưa biết userId."
)

MAX_MEMBER_IDS = 50


def _as_dict(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def create_get_group_info_tool(ctx: ToolContext) -> FunctionTool[NoArgs]:
    message = ctx.message

    async def handler(_args: NoArgs) -> object:
        channel = require_channel(ctx)
        if isinstance(channel, dict):
            return channel
        if not message.is_group:
            return ket_qua_loi("Đây là chat riêng, không phải nhóm")
        if not isinstance(channel, GroupChannel):
            return ket_qua_loi("Lấy thông tin nhóm thất bại: kênh chat hiện tại không hỗ trợ")
        try:
            info = await channel.get_group_info(message.thread_id)
            grid = _as_dict(_as_dict(info.get("gridInfoMap")).get(message.thread_id))
            group = grid or info

            name = group.get("name") or "(không rõ tên)"
            member_ids_raw = group.get("memVerList")
            member_ids: list[object]
            if isinstance(member_ids_raw, list):
                member_ids = cast("list[object]", member_ids_raw)
            else:
                fallback = group.get("memberIds")
                member_ids = cast("list[object]", fallback) if isinstance(fallback, list) else []
            total_member = group.get("totalMember")
            if total_member is None:
                total_member = len(member_ids) if isinstance(group.get("memberIds"), list) else "?"

            # memVerList items look like "uid_ver": cut to take the uid
            members = ", ".join(str(m).split("_")[0] for m in member_ids[:MAX_MEMBER_IDS])

            return "\n".join(
                [
                    f"Tên nhóm: {name}",
                    f"Số thành viên: {total_member}",
                    f"Member ids (tối đa 50): {members or '(không đọc được)'}",
                ]
            )
        except Exception as err:
            return ket_qua_loi(f"Lấy thông tin nhóm thất bại: {err}")

    return FunctionTool(name="get_group_info", description=DESCRIPTION, input_model=NoArgs, handler=handler)
