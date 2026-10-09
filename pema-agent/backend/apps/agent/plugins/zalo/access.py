# ported from: src/middleware/allowlist-filter.ts
"""Decide whether the bot answers a message. Runs BEFORE any LLM call, so a filtered message costs no token.

Pure: the account settings and the message in, the decision out. ``record`` (passive listening: keep a group
message as context without answering) is decided as in the original, but the agent core has no path yet for a
message that is kept and not answered, so the plugin drops those for now.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inbound import ZaloInbound
from .models import AccountConfig, AllowlistMode


@dataclass(frozen=True)
class FilterDecision:
    respond: bool
    """Does the bot run the agent and answer."""
    record: bool
    """Do not answer, but keep it as context (passive listening)."""
    reason: str


def _skip(reason: str) -> FilterDecision:
    return FilterDecision(respond=False, record=False, reason=reason)


def _record_only(reason: str) -> FilterDecision:
    return FilterDecision(respond=False, record=True, reason=reason)


def should_respond(account: AccountConfig, msg: ZaloInbound) -> FilterDecision:
    if msg.is_self:
        return _skip("tin của chính bot")

    if not msg.text.strip() and len(msg.image_urls) == 0:
        return _skip("không có nội dung xử lý được (sticker/voice/...)")

    if msg.is_group:
        if not account.respond_to_groups:
            return _skip("account tắt trả lời group")
        if account.group_require_mention and not msg.mentions_me:
            if account.group_passive_listen:
                return _record_only("group không @mention - chỉ ghi history")
            return _skip("group yêu cầu @mention bot")

    if account.allowlist.mode is AllowlistMode.LIST and msg.sender_id not in account.allowlist.user_ids:
        return _skip("sender ngoài allowlist")

    return FilterDecision(respond=True, record=True, reason="ok")
