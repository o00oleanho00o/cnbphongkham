# ported from: src/middleware/allowlist-filter.ts
"""Decide whether the bot answers a message. Runs BEFORE any LLM call, so a filtered message costs no token.

Forced deviations: ``ParsedMessage`` is ``pema_contracts.channel.InboundMessage`` and ``AccountConfig`` is the
contract DTO (``respond_to_groups``, ``group_require_mention``, ``group_passive_listen``, ``allowlist``).
The function stays pure: the per-thread kill switch is read by the caller from the thread store, so this
module (and its tests) need no database.
"""

from __future__ import annotations

from dataclasses import dataclass

from pema_contracts.agents import AccountConfig, AllowlistMode
from pema_contracts.channel import InboundMessage


@dataclass(frozen=True)
class FilterDecision:
    respond: bool
    """Does the bot run the agent and answer."""
    record: bool
    """Do not answer, but still write to history (passive listening): a group message without an @mention,
    or a thread whose bot is switched off. The next interaction then sees the surrounding context instead
    of only the isolated mentions."""
    reason: str


def _skip(reason: str) -> FilterDecision:
    return FilterDecision(respond=False, record=False, reason=reason)


def _record_only(reason: str) -> FilterDecision:
    return FilterDecision(respond=False, record=True, reason=reason)


def should_respond(
    account: AccountConfig,
    msg: InboundMessage,
    bot_enabled_for_thread: bool = True,
) -> FilterDecision:
    """``shouldRespond``. ``bot_enabled_for_thread``: the per-thread kill switch (table ``agent.threads``)."""
    if msg.is_self:
        return _skip("tin của chính bot")

    if not msg.text.strip() and len(msg.images) == 0:
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

    # The kill switch is checked AFTER the allowlist: someone outside the allowlist must not get a history
    # row even when the thread has the bot switched off.
    if not bot_enabled_for_thread:
        return _record_only("thread đang tắt bot - chỉ ghi history")

    return FilterDecision(respond=True, record=True, reason="ok")
