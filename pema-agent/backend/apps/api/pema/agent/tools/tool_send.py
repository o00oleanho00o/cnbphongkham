# ported from: src/agent/tools/send-attachment-with-caption.ts (shared send plumbing of 5 tools)
"""Plumbing shared by the tools that SEND something straight to the conversation.

Five tools of the original (``send_file``, ``create_word_document``, ``create_excel_file``,
``create_image``, ``tag_member``) called ``enqueueSend`` + ``api.sendMessage`` directly. In the Python
port the Zalo API is behind ``ChannelPort``; the three things every such send needs are gathered here so
none of them can be forgotten:

1. the thread key of the per-thread send queue (``<account_id>:<thread_id>``);
2. the policy gate: every text that would leave the system goes through ``PolicyHooks.on_outbound`` (hook
   table of CONTRACTS-AI01 section 3, origin ``TOOL_SEND``). A tool send cannot be "held for review" (the
   file or mention is already built), so anything but ``SEND`` refuses the call with a message the model
   can read. The media/web/``tag_member`` tools are switched off in ``patient_channel`` anyway; this is
   the second lock;
3. reporting the sent text back to the caller (``ToolContext.record_sent``, ``ghiNhanDaGui``) so it enters
   history."""

from __future__ import annotations

from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import KetQuaLoiTool, ket_qua_loi
from pema_contracts.channel import ChannelPort, SendResult, SendStatus
from pema_contracts.policy import OutboundAction, OutboundOrigin
from pema_contracts.tools import ToolContext


def thread_key_of(ctx: ToolContext) -> str:
    """``<accountId>:<threadId>``: key of the send queue that keeps the order of messages inside a thread."""
    return f"{ctx.account.id}:{ctx.message.thread_id}"


def require_channel(ctx: ToolContext) -> ChannelPort | KetQuaLoiTool:
    """``apiCaNhan``: the tool needs a channel, and in a real turn the registry only builds it when the
    channel can do the work. ``ctx.channel`` is ``None`` only in tests and in scheduled turns of a stopped
    account."""
    if ctx.channel is None:
        return ket_qua_loi(
            "Tool này cần kênh chat đang chạy nhưng lượt hiện tại không có kênh - "
            "lẽ ra nó đã bị loại khỏi lượt này. Nói thật với người dùng là chưa làm được."
        )
    return ctx.channel


async def outbound_refusal(ctx: ToolContext, deps: ToolDeps, text: str) -> KetQuaLoiTool | None:
    """``None`` when the policy lets ``text`` leave; otherwise the failure to return to the model."""
    decision = await deps.policy.on_outbound(
        ctx.policy, text, proactive=ctx.isolated, origin=OutboundOrigin.TOOL_SEND
    )
    if decision.action is OutboundAction.SEND:
        return None
    return ket_qua_loi(
        "Chính sách của kênh này không cho tool gửi thẳng tin cho khách (cần người duyệt). "
        "Nói thật với người dùng là chưa gửi được, đừng hứa gửi sau."
    )


def send_result_failure(result: SendResult) -> KetQuaLoiTool | None:
    """A guard of the channel answers a rejected ``SendResult`` instead of raising: turn it into a failure."""
    if result.status is SendStatus.REJECTED:
        code = result.error_code.value if result.error_code is not None else "rejected"
        return ket_qua_loi(f"Kênh từ chối gửi ({code}). Nói thật với người dùng là chưa gửi được.")
    return None


async def send_plain_text(ctx: ToolContext, deps: ToolDeps, text: str) -> SendResult | KetQuaLoiTool:
    """Send ONE plain text part through the queue and the policy gate (the "đang vẽ ảnh..." notices)."""
    channel = require_channel(ctx)
    if isinstance(channel, dict):
        return channel
    refusal = await outbound_refusal(ctx, deps, text)
    if refusal is not None:
        return refusal

    async def _send() -> SendResult:
        return await channel.send_text(
            ctx.message.thread_id, text, thread_kind=ctx.message.thread_kind, proactive=ctx.isolated
        )

    return await deps.send_queue.enqueue_send(thread_key_of(ctx), _send)
