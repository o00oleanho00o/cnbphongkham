# ported from: src/middleware/allowlist-filter.ts
"""Decide whether the bot answers a message. Runs BEFORE any LLM call, so a filtered message costs no token.

Pure: the account settings and the message in, the decision out. The channel tells the plugins that listen
(``ctx.observe``, for instance ``conversations``) of every message, answered or not, but only of the groups
the account is set to listen to (``keeps_chat``); the agent runs a turn only for the ones this decision
answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inbound import ZaloInbound
from .models import AccountConfig, AllowlistMode


@dataclass(frozen=True)
class FilterDecision:
    respond: bool
    """Does the bot run the agent and answer."""
    reason: str


def _skip(reason: str) -> FilterDecision:
    return FilterDecision(respond=False, reason=reason)


def keeps_chat(account: AccountConfig, *, thread_id: str, is_group: bool) -> bool:
    """Is this chat one the account keeps conversations of: every one-to-one chat, and a group only when it is
    on the account's list. A group not on it is still answered when the account is asked in it."""
    return not is_group or thread_id in account.listen_group_ids


def should_respond(account: AccountConfig, msg: ZaloInbound) -> FilterDecision:
    if msg.is_self:
        return _skip("tin của chính bot")

    if not msg.text.strip() and len(msg.image_urls) == 0:
        return _skip("không có nội dung xử lý được (sticker/voice/...)")

    if msg.is_group:
        # Two lists, never mixed: the group list decides in a group (anyone in an allowed group may ask), the
        # people list decides in a one-to-one chat.
        if not account.respond_to_groups:
            return _skip("account tắt trả lời group")
        if (
            account.group_allowlist.mode is AllowlistMode.LIST
            and msg.thread_id not in account.group_allowlist.group_ids
        ):
            return _skip("group ngoài danh sách nhóm")
        if account.group_require_mention and not msg.mentions_me:
            return _skip("group yêu cầu @mention bot")
    elif account.allowlist.mode is AllowlistMode.LIST and msg.sender_id not in account.allowlist.user_ids:
        return _skip("sender ngoài allowlist")

    return FilterDecision(respond=True, reason="ok")
