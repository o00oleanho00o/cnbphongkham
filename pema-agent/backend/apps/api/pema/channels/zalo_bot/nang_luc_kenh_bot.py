# ported from: src/zalo-bot/nang-luc-kenh-bot.ts
"""Which tools CAN run on the Zalo Bot channel and which cannot, with the reason.

Why this table instead of letting the tool run and fail: the sender would think the agent is broken, when it
is a LIMIT OF THE PLATFORM. A tool blocked here does not enter the schema sent to the model, so the model
cannot promise what it cannot do (the capability section of the prompt is built from exactly the filtered tool
set).

Every "unsupported" line below is MEASURED ON THE REAL API on 2026-08-11, not inferred from the documentation:
17 methods probed, 13 answered ``{"ok":false,"description":"Not Found","error_code":404}`` with HTTP 200.

Forced deviation: the table is also exposed as DATA of the channel (``ChannelCapabilities.blocked_tools`` and
``persona_rule``, CONTRACTS decision 10), through ``ZALO_BOT_CAPABILITIES`` which ``ZaloBotChannel`` returns.
"""

from __future__ import annotations

from dataclasses import dataclass

from pema_contracts.channel import ZALO_BOT_MAX_TEXT_CHARS, ChannelCapabilities, ChannelKind


@dataclass(frozen=True)
class LyDoKhongHoTro:
    """Why a tool is not usable; shown to the operator on the dashboard."""

    hint: str
    """A short sentence for the Tools page."""


TOOL_KHONG_CHAY_TREN_BOT: dict[str, LyDoKhongHoTro] = {
    "send_file": LyDoKhongHoTro(
        hint="Zalo Bot API không có method gửi file (đo thật: sendDocument/sendFile đều trả 404)"
    ),
    "create_word_document": LyDoKhongHoTro(
        hint="Tạo được file nhưng không gửi được - Zalo Bot API không có method gửi tài liệu"
    ),
    "create_excel_file": LyDoKhongHoTro(
        hint="Tạo được file nhưng không gửi được - Zalo Bot API không có method gửi tài liệu"
    ),
    # ``sendPhoto`` EXISTS, but only takes a public URL: multipart returns "The photo must not be empty", a
    # data URI and base64 return "The photo must start with http:// or https://". An image the bot drew sits
    # on disk so it cannot be sent directly. Can be reopened if a route that serves images over HTTPS appears
    # later.
    "create_image": LyDoKhongHoTro(
        hint=(
            "Zalo Bot API chỉ gửi ảnh qua URL công khai, không nhận file tải lên - "
            "cần đường phục vụ ảnh qua HTTPS trước"
        )
    ),
    # No method that sends video exists in the Bot API client, and this tool is built on ``sendVideo`` of the
    # personal-account library, which a bot channel does not have.
    "tai_video": LyDoKhongHoTro(hint="Zalo Bot API không có method gửi video"),
    "add_reaction": LyDoKhongHoTro(
        hint="Zalo Bot API không có method thả cảm xúc (setMessageReaction trả 404)"
    ),
    "tag_member": LyDoKhongHoTro(hint="Zalo Bot API không có method tag thành viên trong nhóm"),
    # ``schedule_task`` USED to be here, and it was the ONLY entry that cited neither a 404 measurement nor a
    # hard constraint: the real reason was that the scheduler was hard wired to the personal-account library,
    # so a bot account never had a send path. The Bot API can message proactively (measured: 10 messages in
    # 416 ms, not blocked). It was wired in ``scheduled-job-reply-target`` (roadmap V3.19).
    "get_group_info": LyDoKhongHoTro(
        hint="Zalo Bot API không có method đọc thông tin nhóm (getChat/getChatMember trả 404)"
    ),
}
"""Tools that do NOT run on the bot channel. A tool with no name here runs normally.

Kept as a BLOCK list, not an ALLOW list: pure tools (not touching the channel) are the majority and will stay
the majority, so the block list is shorter and needs fewer edits each time a tool is added."""


def tool_chay_duoc_tren_bot(key: str) -> bool:
    return key not in TOOL_KHONG_CHAY_TREN_BOT


LUAT_PERSONA_KENH_BOT = (
    "- Bạn đang chạy trên TÀI KHOẢN BOT của Zalo. Kênh này KHÔNG gửi được file, "
    "tài liệu Word/Excel, ảnh tự vẽ, video tải về, không thả được cảm xúc, không tag được ai "
    "trong nhóm và không xem được danh sách thành viên nhóm - đó là giới hạn của "
    "nền tảng Zalo, KHÔNG phải bạn bị lỗi. Ai nhờ mấy việc đó thì nói thẳng là tài "
    "khoản bot không làm được, và mời họ nhắn qua tài khoản cá nhân nếu cần. Đừng "
    "hứa rồi im, cũng đừng xin lỗi vòng vo."
)
"""Line appended to the persona when the turn runs on the bot channel.

Hiding the tool is NOT enough: the model would answer "I cannot do that" without saying why, and the sender
would think the agent is broken. This line lets the model state the real cause and point to a usable channel.
"""


ZALO_BOT_CAPABILITIES = ChannelCapabilities(
    channel=ChannelKind.ZALO_BOT,
    supports_inbound=True,
    # The Bot API can message proactively (measured: 10 messages in 416 ms). The proactive GUARD (cap, window,
    # gap, kill switch) is package S's ``ProactiveSendGuard``; the channel only declares what it can do.
    can_send_proactive=True,
    daily_cap=None,
    requires_friend=False,
    max_text_length=ZALO_BOT_MAX_TEXT_CHARS,
    # The Bot API does not understand ``styles``: declared EXPLICITLY instead of dropped quietly at the send
    # path. The splitter counts ``styles`` into the byte budget, so dropping only at the last moment would
    # still charge a few hundred bytes per message and sometimes split into two messages for nothing.
    supports_formatting=False,
    # The Bot API has no quoting (measured: no method).
    supports_quote=False,
    supports_typing_indicator=True,
    supports_read_receipt=False,
    supports_reactions=False,
    supports_send_image=False,
    supports_send_file=False,
    supports_send_video=False,
    supports_group_info=False,
    supports_tag_member=False,
    blocked_tools={key: reason.hint for key, reason in TOOL_KHONG_CHAY_TREN_BOT.items()},
    persona_rule=LUAT_PERSONA_KENH_BOT,
)
