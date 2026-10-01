# ported from: src/agent/tools/send-attachment-with-caption.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Safety net for the caption that goes with a file/image. It differs from a chat turn in the size of the
damage: at this point the .docx/.xlsx is already built, or the image already drawn (60-135 seconds).
Losing all that because of one caption line with an odd format is the most expensive way to fail.

Forced deviation (see the module docstring of ``send_attachment_with_caption``): ``MediaChannel`` has no
slot for caption styles, so there is never a styled send to retry as plain text. The original cases about
the "Zalo rejected the styled caption (code 112) -> resend as plain text" fallback therefore become: the
caption goes out as clean plain text in ONE attempt; a rejected or failed send is never re-sent (a
transport error means the file may already have arrived, re-sending doubles it in front of the user)."""

from __future__ import annotations

import pytest

from pema.agent.tools.send_attachment_with_caption import MediaSendError, gui_file_kem_caption
from pema.agent.tools.testing import RecordingChannel, make_channel, make_tool_context, make_tool_deps
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.errors import ErrorCode


async def _send(channel: RecordingChannel, caption: str | None, *, as_image: bool = False) -> None:
    ctx = make_tool_context(channel=channel)
    await gui_file_kem_caption(
        ctx, make_tool_deps(), filename="bao-gia.docx", data=b"PK", caption=caption, as_image=as_image
    )


async def test_gui_file_kem_caption_caption_goes_out_as_clean_plain_text_with_the_file_attached() -> None:
    """caption có định dạng: markdown bị dọn, FILE VẪN ĐI KÈM trong cùng một lần gửi"""
    channel = make_channel()
    await _send(channel, "Báo giá **tháng 8** đây ạ")

    assert len(channel.media) == 1
    assert channel.media[0].caption == "Báo giá tháng 8 đây ạ", "chữ caption phải sạch dấu markdown"
    assert channel.media[0].filename == "bao-gia.docx"
    assert channel.media[0].data == b"PK", "mất file đính kèm là hỏng nặng hơn cả lỗi ban đầu"


async def test_gui_file_kem_caption_transport_error_is_not_resent_the_file_may_have_arrived() -> None:
    """lỗi đứt mạng thì KHÔNG gửi lại - file có thể đã tới, gửi lại là hai file"""
    channel = make_channel(fail_media=RuntimeError("socket hang up"))
    with pytest.raises(RuntimeError, match="socket hang up"):
        await _send(channel, "Báo giá **tháng 8**")
    assert channel.media == []


async def test_gui_file_kem_caption_rejected_send_is_reported_once_and_never_resent() -> None:
    """máy chủ từ chối thì báo hỏng đúng một lần, không gửi lại lần hai"""
    rejected = SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE)
    channel = make_channel(reject_media=rejected)
    with pytest.raises(MediaSendError, match="từ chối"):
        await _send(channel, "File anh cần đây ạ")
    assert len(channel.media) == 1


async def test_gui_file_kem_caption_works_without_a_caption() -> None:
    """không có caption vẫn gửi được file"""
    channel = make_channel()
    await _send(channel, None)

    assert len(channel.media) == 1
    assert channel.media[0].caption == ""
    assert channel.media[0].data == b"PK"


async def test_gui_file_kem_caption_an_image_goes_through_send_image() -> None:
    """ảnh đi bằng send_image, file đi bằng send_file (ca bổ sung cho Python)"""
    channel = make_channel()
    await _send(channel, "ảnh đây", as_image=True)
    assert channel.media[0].kind == "image"


async def test_gui_file_kem_caption_a_channel_without_media_ability_is_reported() -> None:
    """kênh không có năng lực gửi file (Bot API) thì báo hỏng rõ ràng, không ném lỗi thuộc tính"""
    from pema_contracts.testing import FakeChannel

    channel = FakeChannel(caps=make_channel().caps)
    ctx = make_tool_context(channel=channel)
    with pytest.raises(MediaSendError, match="không hỗ trợ"):
        await gui_file_kem_caption(ctx, make_tool_deps(), filename="a.docx", data=b"x", caption=None)
