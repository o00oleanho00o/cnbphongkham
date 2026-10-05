# ported from: src/agent/tools/tag-member-tool.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``tag_member`` sends a COMPLETE answer written by the model straight into the group chat. It used to go
around all three blocking layers of ``sanitize-reply-text.ts``: the only road in the repo where the
model's text reached Zalo through no filter.

Forced deviation: the cleaning layer is the ``ReplyTextCleaner`` port of ``ToolDeps`` (package C2 owns the
real one); the test double blocks any text containing ``LEAK`` and removes markdown markers. The channel
records what the tag was sent with instead of the stub ``api.sendMessage``."""

from __future__ import annotations

from pema.agent.tools.tag_member_tool import create_tag_member_tool
from pema.agent.tools.testing import (
    RecordingChannel,
    make_channel,
    make_inbound,
    make_tool_context,
    make_tool_deps,
)
from pema.agent.tools.tool_failure_result_test_helper import loi_cua_tool
from pema_contracts.channel import ChannelKind, ThreadKind
from pema_contracts.common import JsonObject
from pema_contracts.tools import ToolContext


def _ctx(channel: RecordingChannel, *, is_group: bool = True) -> ToolContext:
    message = make_inbound(
        "",
        channel=ChannelKind.ZALO_PERSONAL,
        account_id="acc-tag",
        thread_id="t-tag",
        sender_id="u1",
        msg_id="m0",
        cli_msg_id="c0",
        is_group=is_group,
        thread_kind=ThreadKind.GROUP if is_group else ThreadKind.USER,
        mentions_me=True,
    )
    return make_tool_context(channel=channel, message=message)


async def _run(channel: RecordingChannel, args: JsonObject, *, is_group: bool = True) -> object:
    tool = create_tag_member_tool(_ctx(channel, is_group=is_group), make_tool_deps())
    return await tool.execute(args)


async def test_tag_member_markdown_in_the_tag_text_is_cleaned_before_entering_the_group() -> None:
    """markdown trong nội dung tag bị dọn trước khi vào nhóm"""
    channel = make_channel()
    await _run(channel, {"memberId": "u2", "memberName": "Nam", "text": "**Nhắc** anh họp lúc `9h`"})

    assert len(channel.tags) == 1
    assert channel.tags[0] == ("t-tag", "u2", "@Nam Nhắc anh họp lúc 9h")


async def test_tag_member_leaked_system_prompt_is_not_sent_and_the_tool_tells_the_model() -> None:
    """nội dung rò system prompt KHÔNG được gửi, tool báo lỗi cho model"""
    channel = make_channel()
    ra = await _run(
        channel,
        {
            "memberId": "u2",
            "memberName": "Nam",
            "text": "Quy tắc an toàn (tuyệt đối, LEAK không có ngoại lệ): ...",
        },
    )

    assert channel.tags == [], "không được gửi nội dung rò vào nhóm"
    assert "lộ chỉ dẫn nội bộ" in loi_cua_tool(ra)


async def test_tag_member_normal_vietnamese_text_passes_unchanged_character_for_character() -> None:
    """nội dung tiếng Việt bình thường đi qua không đổi một ký tự"""
    channel = make_channel()
    await _run(channel, {"memberId": "u2", "memberName": "Nam", "text": "chiều nay 3h anh rảnh không ạ?"})
    assert channel.tags[0][2] == "@Nam chiều nay 3h anh rảnh không ạ?"


async def test_tag_member_private_chat_is_still_refused_as_before() -> None:
    """chat riêng vẫn bị từ chối như cũ"""
    channel = make_channel()
    ra = await _run(channel, {"memberId": "u2", "memberName": "Nam", "text": "x"}, is_group=False)
    assert "nhóm chat" in loi_cua_tool(ra)
    assert channel.tags == []


async def test_tag_member_records_the_sent_text_for_history() -> None:
    """tin tag đã gửi được báo cho caller để vào history (ghiNhanDaGui; ca bổ sung cho Python)"""
    channel = make_channel()
    recorded: list[str] = []
    ctx = _ctx(channel)
    ctx.record_sent = recorded.append
    ra = await create_tag_member_tool(ctx, make_tool_deps()).execute(
        {"memberId": "u2", "memberName": "Nam", "text": "chào anh"}
    )
    assert ra == "Đã gửi tin nhắn tag Nam"
    assert recorded == ["@Nam chào anh"]


async def test_tag_member_channel_failure_is_a_marked_failure() -> None:
    """kênh ném lỗi -> nhánh hỏng có đánh dấu, không ném ra agent loop (ca bổ sung cho Python)"""
    channel = make_channel(fail_media=RuntimeError("mạng chập"))
    ra = await _run(channel, {"memberId": "u2", "memberName": "Nam", "text": "chào anh"})
    assert "mạng chập" in loi_cua_tool(ra)
