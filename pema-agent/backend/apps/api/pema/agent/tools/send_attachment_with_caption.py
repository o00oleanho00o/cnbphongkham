# ported from: src/agent/tools/send-attachment-with-caption.ts
"""Send a file/image with a caption.

Three tools (``send_file`` and the 2 document tools) and ``create_image`` used to each call
``enqueueSend`` with the same shape. They were gathered because the safety net must sit in ONE place:
spread over four places, sooner or later one is forgotten, and here "forgotten" means a file already built
and lost because of one caption line.

Forced deviations:

* ``api.sendMessage({msg, styles, attachments: [filePath]})`` of zca-js becomes ``MediaChannel.send_file``
  / ``send_image`` (bytes + caption). The contract has NO slot for caption styles, so the caption travels
  as the cleaned plain text of ``tin_kem_file`` (markdown markers removed, no bold). Consequently the
  original fallback "Zalo rejected the styled caption -> resend as plain text" (code 112) has nothing to
  retry: there is never a styled send to retry from. A rejected send is reported as a failure and, like
  the original for transport errors, is NEVER re-sent (re-sending doubles the file in front of the user).
  Open item for package G: add an optional ``styles`` argument to ``MediaChannel`` and restore the
  fallback (``tin_kem_file`` already computes the styles).
* the temp file is gone: the channel takes the bytes (the Node bridge receives them over HTTP), so
  ``withTempFile`` is not needed on this path.
* every send passes the policy gate of ``tool_send`` (``PolicyHooks.on_outbound``, origin ``TOOL_SEND``).
"""

from __future__ import annotations

from pema.agent.tools.clean_tool_caption import tin_kem_file
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_send import outbound_refusal, require_channel, thread_key_of
from pema_contracts.channel import MediaChannel, SendResult, SendStatus
from pema_contracts.tools import ToolContext


class MediaSendError(Exception):
    """The attachment was not sent. The message is Vietnamese text for the model (no PII, no file content)."""


async def gui_file_kem_caption(
    ctx: ToolContext,
    deps: ToolDeps,
    *,
    filename: str,
    data: bytes,
    caption: str | None,
    as_image: bool = False,
) -> None:
    """Send ``data`` to the conversation of ``ctx`` through the per-thread queue. Raises
    ``MediaSendError`` when the channel cannot, the policy refuses, or the channel rejects; transport
    errors propagate."""
    channel = require_channel(ctx)
    if isinstance(channel, dict):
        raise MediaSendError(channel["loi"])
    if not isinstance(channel, MediaChannel):
        raise MediaSendError("Kênh chat hiện tại không hỗ trợ gửi file hoặc ảnh")

    tin = tin_kem_file(caption, deps.reply_cleaner, deps.markdown_styler)
    refusal = await outbound_refusal(ctx, deps, tin.msg or filename)
    if refusal is not None:
        raise MediaSendError(refusal["loi"])

    thread_id = ctx.message.thread_id
    thread_kind = ctx.message.thread_kind

    async def _send() -> SendResult:
        if as_image:
            return await channel.send_image(thread_id, thread_kind, data, tin.msg)
        return await channel.send_file(thread_id, thread_kind, filename, data, tin.msg)

    result = await deps.send_queue.enqueue_send(thread_key_of(ctx), _send)
    if result.status is SendStatus.REJECTED:
        code = result.error_code.value if result.error_code is not None else "rejected"
        raise MediaSendError(f"Kênh từ chối gửi ({code})")
