# ported from: src/agent/tools/add-reaction-tool.ts
"""``add_reaction``: drop a reaction on the message the user just sent.

Forced deviation: ``api.addReaction(Reactions.X, {data: {msgId, cliMsgId}, threadId, type})`` of zca-js
becomes ``ReactionChannel.react(message, icon)`` with the icon NAME (``heart``, ``like``...); the personal
channel maps the name to the zca-js constant. The Bot API channel has no reaction and the tool is blocked
there (``ChannelCapabilities.blocked_tools``), so ``build`` never runs without the ability."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.tool_send import require_channel, send_result_failure
from pema_contracts.channel import ReactionChannel
from pema_contracts.tools import ToolContext

REACTION_NAMES = ("heart", "like", "haha", "wow", "cry", "angry", "ok", "rose")
"""``REACTION_MAP`` keys; the channel owns the mapping to its own constants."""


class AddReactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction: Literal["heart", "like", "haha", "wow", "cry", "angry", "ok", "rose"] = Field(
        description="Loại reaction"
    )


DESCRIPTION = (
    "Thả reaction (biểu tượng cảm xúc) vào tin nhắn người dùng vừa gửi. Dùng khi muốn phản hồi cảm xúc "
    "nhẹ nhàng kèm/thay cho trả lời chữ."
)


def create_add_reaction_tool(ctx: ToolContext) -> FunctionTool[AddReactionInput]:
    message = ctx.message

    async def handler(args: AddReactionInput) -> object:
        if not message.msg_id:
            return ket_qua_loi("Không thả được reaction: tin nhắn không có msgId")
        channel = require_channel(ctx)
        if isinstance(channel, dict):
            return channel
        if not isinstance(channel, ReactionChannel):
            return ket_qua_loi("Thả reaction thất bại: kênh chat hiện tại không hỗ trợ reaction")
        try:
            result = await channel.react(message, args.reaction)
        except Exception as err:
            return ket_qua_loi(f"Thả reaction thất bại: {err}")
        failure = send_result_failure(result)
        if failure is not None:
            return ket_qua_loi(f"Thả reaction thất bại: {failure['loi']}")
        return f"Đã thả reaction {args.reaction}"

    return FunctionTool(
        name="add_reaction", description=DESCRIPTION, input_model=AddReactionInput, handler=handler
    )
