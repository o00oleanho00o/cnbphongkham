"""Zalo Official Account (OA) / ZNS channel: a STUB.

There is no Zalo OA or ZNS contract yet (PLAN-AI01 section 8: "no Zalo OA/ZNS yet, only the Bot API and the
personal account"). This class exists so ``ChannelKind.ZALO_OA`` has a named home and a registry or router
that meets it fails loudly instead of silently. Every ability raises ``NotImplementedError``.

TODO(AI01-OA): chờ có Zalo OA/ZNS. When the clinic has an OA, implement ``ChannelPort`` here (webhook
signature, the 7-day interaction window and ZNS templates are OA-API rules; none of them apply to the Bot
API).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    InboundMessage,
    QuoteRef,
    SendResult,
    TextStyle,
    ThreadKind,
)

_NOT_AVAILABLE = "Zalo OA/ZNS chưa có (TODO(AI01-OA): chờ có Zalo OA/ZNS)"


class ZaloOaChannel:
    def __init__(self, account_id: str = "") -> None:
        self._account_id = account_id

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.ZALO_OA

    @property
    def account_id(self) -> str:
        return self._account_id

    def capabilities(self) -> ChannelCapabilities:
        raise NotImplementedError(_NOT_AVAILABLE)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        raise NotImplementedError(_NOT_AVAILABLE)

    def parse_inbound(self, update: Mapping[str, object]) -> InboundMessage | None:
        raise NotImplementedError(_NOT_AVAILABLE)

    async def send_text(
        self,
        thread_id: str,
        text: str,
        *,
        thread_kind: ThreadKind = ThreadKind.USER,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        proactive: bool = False,
    ) -> SendResult:
        raise NotImplementedError(_NOT_AVAILABLE)
