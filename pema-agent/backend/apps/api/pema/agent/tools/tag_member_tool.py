# ported from: src/agent/tools/tag-member-tool.ts
"""``tag_member``: send a message that tags (@mention) a member of the group.

Forced deviation: ``api.sendMessage({msg, mentions: [{pos: 0, uid, len}]}, threadId, type)`` of zca-js
becomes ``GroupChannel.tag_member(thread_id, member_id, text)`` where ``text`` is the full text that
STARTS with the ``@<name>`` mention (the mention is always at position 0, with the length of ``@<name>``);
the channel derives the mention span from it. Open item for package G: the contract has no ``member_name``
/ mention length argument.

``text`` is a COMPLETE answer written by the model and sent straight into the group, so it must pass the
same cleaning layer as a normal answer, otherwise it is a detour around all three blocking layers (it used
to be the only road in the repo on which the model's text reached Zalo through no filter)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.sent_by_tool_note import ghi_chu_da_gui_chu
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.tool_send import (
    outbound_refusal,
    require_channel,
    send_result_failure,
    thread_key_of,
)
from pema_contracts.channel import GroupChannel, SendResult
from pema_contracts.tools import ToolContext

DESCRIPTION = (
    "Gửi tin nhắn có tag (@mention) một thành viên trong nhóm. Chỉ dùng trong group chat, cần biết đúng "
    "userId (lấy từ get_group_info nếu chưa biết)."
)


class TagMemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: str = Field(alias="memberId", description="userId của thành viên cần tag")
    member_name: str = Field(alias="memberName", description="Tên hiển thị của thành viên")
    text: str = Field(description="Nội dung nhắn kèm sau phần tag")


def create_tag_member_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[TagMemberInput]:
    message = ctx.message

    async def handler(args: TagMemberInput) -> object:
        if not message.is_group:
            return ket_qua_loi("Chỉ tag được trong nhóm chat")
        channel = require_channel(ctx)
        if isinstance(channel, dict):
            return channel
        if not isinstance(channel, GroupChannel):
            return ket_qua_loi("Tag thất bại: kênh chat hiện tại không hỗ trợ tag thành viên")

        # ``text`` is a COMPLETE answer written by the model and sent straight into the group, so it must
        # go through the very same cleaning layer as a normal answer, else it is a detour around all three
        # layers.
        sach = deps.reply_cleaner.clean_reply(args.text)
        if sach.blocked:
            return ket_qua_loi(
                "Nội dung định tag có dấu hiệu lộ chỉ dẫn nội bộ nên chưa gửi được. "
                "Viết lại bằng lời của bạn rồi thử lại."
            )
        noi_dung = sach.text.strip() or args.text

        mention_text = f"@{args.member_name}"
        full_text = f"{mention_text} {noi_dung}"
        refusal = await outbound_refusal(ctx, deps, full_text)
        if refusal is not None:
            return refusal

        async def _send() -> SendResult:
            return await channel.tag_member(message.thread_id, args.member_id, full_text)

        try:
            result = await deps.send_queue.enqueue_send(thread_key_of(ctx), _send)
        except Exception as err:
            return ket_qua_loi(f"Tag thất bại: {err}")
        failure = send_result_failure(result)
        if failure is not None:
            return ket_qua_loi(f"Tag thất bại: {failure['loi']}")
        if ctx.record_sent is not None:
            ctx.record_sent(ghi_chu_da_gui_chu(full_text))
        return f"Đã gửi tin nhắn tag {args.member_name}"

    return FunctionTool(
        name="tag_member", description=DESCRIPTION, input_model=TagMemberInput, handler=handler
    )
