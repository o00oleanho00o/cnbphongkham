# ported from: src/zalo/kenh-ca-nhan.ts (+ duongGuiZcaJs of src/zalo/send-reply-in-parts.ts, tuThaCamXuc)
"""Kênh TÀI KHOẢN CÁ NHÂN (zca-js qua bridge) - đủ cả 5 năng lực.

``kenhCaNhan(api)`` returned the ``KenhLuot`` record; here it is ``ZaloPersonalChannel``, the ``ChannelPort``
implementation of ``pema_contracts.channel`` plus the optional capability Protocols (``TypingChannel``,
``ReadReceiptChannel``, ``ReactionChannel``, ``MediaChannel``, ``GroupChannel``):

| Năng lực (KenhLuot)      | Here                                                                  |
|---|---|
| ``duongGui``             | ``send_text`` (one part; the pipeline splits, see ``send_reply_in_parts``) |
| ``batDangNhap``          | ``start_typing``                                                      |
| ``baoDaXem``             | ``mark_seen`` (fire-and-forget through ``message_receipts``)          |
| ``tuThaCamXuc``          | ``auto_react`` (best effort, never raises) + ``react`` (tool)         |
| ``api`` for tools        | ``MediaChannel`` / ``GroupChannel`` methods                           |

PHẢI GIỮ THUẦN (không state riêng, không bộ nhớ đệm giữa các lời gọi) như bản gốc: the only state is the
``ProactiveGate`` (friend cache, last proactive instant), which exists once per account and is the whole point
of the clinic safety layer.

Forced deviations: the zca-js ``API`` is the bridge-backed ``ZaloApi``; a guard (kill switch, flag, window,
friend, cap) is a REJECTED ``SendResult`` (contract), whereas a server refusal or a transport failure still
RAISES ``ZaloBridgeError`` so ``send_reply_in_parts`` keeps its retry-without-styles rule untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from pema.channels.zalo_personal.bridge_client import ZaloApi, ZaloBridgeError
from pema.channels.zalo_personal.bridge_signing import verify_signature
from pema.channels.zalo_personal.message_receipts import send_seen_receipt
from pema.channels.zalo_personal.proactive_gate import ProactiveGate
from pema.channels.zalo_personal.reaction_icons import to_zalo_reaction
from pema.channels.zalo_personal.typing_indicator import start_typing_indicator
from pema.channels.zalo_personal.zalo_message_parser import parse_incoming_message
from pema.config.runtime_tuning_settings import get_tuning, get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    InboundMessage,
    QuoteRef,
    SendResult,
    SendStatus,
    TextStyle,
    ThreadKind,
)
from pema_contracts.common import JsonObject, now_vn
from pema_contracts.errors import ErrorCode

log = create_logger("kenh-ca-nhan")

_GUARD_KINDS: dict[str, ErrorCode] = {
    "kill_switch": ErrorCode.CHANNEL_KILL_SWITCH_ON,
    "bridge_disabled": ErrorCode.CHANNEL_UNAVAILABLE,
    "not_running": ErrorCode.CHANNEL_UNAVAILABLE,
    "blocked": ErrorCode.CHANNEL_UNAVAILABLE,
    "unauthorized": ErrorCode.CHANNEL_UNAVAILABLE,
    "rate_limited": ErrorCode.RATE_LIMITED,
}
"""Bridge refusals that mean "the bridge did not even try": reported as a rejected result, never retried."""


def duong_gui_zca_js(
    api: ZaloApi, thread_id: str, thread_type: ThreadKind, *, proactive: bool = False
) -> Callable[..., object]:
    """``duongGuiZcaJs``: the send path of ONE thread over a ``ZaloApi``.

    Only attaches ``styles`` when there are any and ``quote`` when present: zca-js builds
    ``textProperties`` only for
    a non-empty ``styles`` and switches to the ``.../quote`` endpoint when a quote is given, so an empty value
    would change the API call for nothing. One factory instead of every caller writing it: three places
    are three
    chances to forget one of the two rules, and forgetting is silent.
    """

    async def gui(doan: object) -> object:
        text: str = getattr(doan, "text")  # noqa: B009 - DoanCanGui, kept untyped to avoid an import cycle
        styles: Sequence[TextStyle] = getattr(doan, "styles", ())
        quote: QuoteRef | None = getattr(doan, "quote", None)
        return await api.send_message(
            text=text,
            thread_id=thread_id,
            thread_type=thread_type,
            styles=styles if styles else (),
            quote=quote,
            proactive=proactive,
        )

    return gui


class ZaloPersonalChannel:
    """``ChannelPort`` of ONE personal account (``account_id``) of one clinic."""

    def __init__(
        self,
        *,
        clinic_id_str: str,
        config: AccountConfig,
        api: ZaloApi,
        gate: ProactiveGate,
        bridge_secret: Callable[[], str | None],
    ) -> None:
        self._clinic = clinic_id_str
        self.config = config
        self.api = api
        self.gate = gate
        self._bridge_secret = bridge_secret

    # ------------------------------------------------------------------------------------ ChannelPort

    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.ZALO_PERSONAL

    @property
    def account_id(self) -> str:
        return self.config.id

    def capabilities(self) -> ChannelCapabilities:
        settings = self.gate.snapshot
        return ChannelCapabilities(
            channel=ChannelKind.ZALO_PERSONAL,
            can_send_proactive=True,
            daily_cap=self.gate.daily_cap(settings),
            requires_friend=settings.requires_friend,
            max_text_length=get_tuning_int("ZALO_MAX_MESSAGE_CHARS"),
            supports_formatting=True,
            supports_quote=True,
            supports_typing_indicator=True,
            supports_read_receipt=True,
            supports_reactions=True,
            supports_send_image=True,
            supports_send_file=True,
            supports_send_video=True,
            supports_group_info=True,
            supports_tag_member=True,
            min_gap_seconds=settings.min_gap_seconds,
            max_gap_seconds=settings.max_gap_seconds,
            send_window_start=settings.send_window_start.strftime("%H:%M")
            if settings.send_window_start
            else None,
            send_window_end=settings.send_window_end.strftime("%H:%M") if settings.send_window_end else None,
        )

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """HMAC-SHA256 of ``timestamp.body`` with ``PEMA_ZALO_BRIDGE_SECRET`` (constant time, 5 minute
        window)."""
        secret = self._bridge_secret()
        return bool(secret) and verify_signature(secret or "", headers, body)

    def parse_inbound(self, update: Mapping[str, object]) -> InboundMessage | None:
        """A bridge ``message`` envelope -> ``InboundMessage``. ``None`` for anything that is not a user
        message
        (other event types, our own echo, a payload without a thread)."""
        if update.get("type") != "message":
            return None
        message = update.get("message")
        if not isinstance(message, Mapping):
            return None
        self_id = update.get("self_id")
        msg = parse_incoming_message(
            self.config.id,
            self_id if isinstance(self_id, str) and self_id else self.api.get_own_id(),
            message,  # pyright: ignore[reportUnknownArgumentType]
            str(get_tuning("ZALO_IMAGE_QUALITY")),
        )
        if msg.is_self or not msg.thread_id:
            return None
        return msg

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
        admission = None
        if proactive:
            admission = await self.gate.admit(thread_id, thread_kind)
            if admission.rejection is not None:
                return admission.rejection
        try:
            sent = await self.api.send_message(
                text=text,
                thread_id=thread_id,
                thread_type=thread_kind,
                styles=styles if styles else (),
                quote=quote,
                proactive=proactive,
            )
        except ZaloBridgeError as err:
            if admission is not None:
                await self.gate.settle(admission, sent=False)
            mapped = _GUARD_KINDS.get(err.kind)
            if mapped is not None:
                return SendResult(status=SendStatus.REJECTED, error_code=mapped, detail=err.kind)
            raise
        except BaseException:
            if admission is not None:
                await self.gate.settle(admission, sent=False)
            raise
        if admission is not None:
            await self.gate.settle(admission, sent=True)
        message_id = sent.get("msg_id")
        return SendResult(
            status=SendStatus.SENT,
            external_message_id=str(message_id) if message_id is not None else None,
            sent_at=now_vn(),
        )

    # ------------------------------------------------------------------------------- TypingChannel

    def start_typing(self, thread_id: str, thread_kind: ThreadKind) -> Callable[[], None]:
        """``batDangNhap``: start the indicator, get back the function that stops it."""
        return start_typing_indicator(self.api.send_typing_event, thread_id, thread_kind)

    # ------------------------------------------------------------------------- ReadReceiptChannel

    async def mark_seen(self, messages: Sequence[InboundMessage]) -> None:
        """``baoDaXem``: fire-and-forget (the receipt task is scheduled and ``mark_seen`` returns)."""
        send_seen_receipt(self.api, messages)

    # ------------------------------------------------------------------------------ ReactionChannel

    async def react(self, message: InboundMessage, icon: str) -> SendResult:
        """``add_reaction`` tool. Unknown icon keys fall back to a heart like the original."""
        await self.api.add_reaction(
            to_zalo_reaction(icon),
            msg_id=message.msg_id,
            cli_msg_id=message.cli_msg_id,
            thread_id=message.thread_id,
            thread_type=message.thread_kind,
        )
        return SendResult(status=SendStatus.SENT, sent_at=now_vn())

    def auto_react(self, msg: InboundMessage) -> None:
        """``tuThaCamXuc``: tell the sender the bot received the message by reacting to it. Not awaited by the
        caller and swallowing every error: a failed reaction must never slow or break the reply path."""
        import asyncio

        if not self.config.auto_react_enabled or not msg.msg_id:
            return

        async def go() -> None:
            try:
                await self.react(msg, self.config.auto_react_icon)
            except Exception as err:
                log.debug("Auto-react thất bại", err=err)

        task = asyncio.get_running_loop().create_task(go())
        _background.add(task)
        task.add_done_callback(_background.discard)

    # --------------------------------------------------------------------------------- MediaChannel

    async def send_image(
        self, thread_id: str, thread_kind: ThreadKind, data: bytes, caption: str
    ) -> SendResult:
        result = await self.api.send_attachment(
            thread_id=thread_id, thread_type=thread_kind, filename="image.png", data=data, caption=caption
        )
        return _sent(result)

    async def send_file(
        self, thread_id: str, thread_kind: ThreadKind, filename: str, data: bytes, caption: str
    ) -> SendResult:
        result = await self.api.send_attachment(
            thread_id=thread_id, thread_type=thread_kind, filename=filename, data=data, caption=caption
        )
        return _sent(result)

    async def send_video(self, thread_id: str, thread_kind: ThreadKind, url: str, caption: str) -> SendResult:
        result = await self.api.send_video(
            thread_id=thread_id, thread_type=thread_kind, video_url=url, caption=caption
        )
        return _sent(result)

    # --------------------------------------------------------------------------------- GroupChannel

    async def get_group_info(self, thread_id: str) -> JsonObject:
        return await self.api.get_group_info(thread_id)

    async def tag_member(
        self, thread_id: str, member_id: str, text: str, *, mention_len: int | None = None
    ) -> SendResult:
        """Message that mentions ``member_id``. ``text`` already starts with the ``@Name`` mention (the tool
        builds ``f"@{name} {body}"`` like the original). The mention covers ONLY ``@Name``: pass its
        UTF-16 length
        as ``mention_len`` (names contain spaces, so it cannot be guessed); without it the mention ends at the
        first space. ``mention_len`` is an additive optional argument beyond
        ``pema_contracts.GroupChannel``."""
        from pema.channels.utf16_text import utf16_len

        length = mention_len if mention_len is not None else utf16_len(text.split(" ", 1)[0])
        result = await self.api.send_message(
            text=text,
            thread_id=thread_id,
            thread_type=ThreadKind.GROUP,
            mentions=[{"pos": 0, "uid": member_id, "len": length}],
        )
        return _sent(result)


_background: set[object] = set()


def _sent(result: JsonObject) -> SendResult:
    message_id = result.get("msg_id")
    return SendResult(
        status=SendStatus.SENT,
        external_message_id=str(message_id) if message_id is not None else None,
        sent_at=now_vn(),
    )
