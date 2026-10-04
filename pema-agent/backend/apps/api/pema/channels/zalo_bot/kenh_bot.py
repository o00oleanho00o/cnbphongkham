# ported from: src/zalo-bot/kenh-bot.ts
"""The Zalo BOT ACCOUNT channel (Zalo Bot API): ``ZaloBotChannel`` implements ``ChannelPort`` (the
``KenhLuot`` of the bot) and the optional ``TypingChannel``. Only 2 of the 5 abilities exist.

``mark_seen`` (``baoDaXem``) and ``react`` (``tuThaCamXuc``) are NOT implemented, they are not stubbed to
raise: measured on the real API no equivalent method exists (``setMessageReaction`` answers 404), and both are
side jobs that the bot can do without. ``isinstance(channel, ReadReceiptChannel)`` is therefore ``False``, as
the contract intends.

Forced deviations:

* ``KenhLuot`` -> ``ChannelPort``: ``duongGui(threadId)`` + ``DoanCanGui`` become ``send_text(thread_id, text,
  ...)`` for ONE part; ``tranKyTuMotTin`` / ``mangDinhDang`` become ``capabilities()``. ``api: null`` is gone
  (the tools get the channel through ``ToolContext.channel``).
* New: ``verify_webhook`` (constant-time compare of the ``X-Bot-Api-Secret-Token`` header) and
  ``parse_inbound``, because Pema also receives webhooks.
* ``send_text`` never raises for an API failure: it answers a rejected ``SendResult`` (contract), with the
  detail already masked of the token.
"""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from pydantic import ValidationError

from pema.channels.zalo_bot.nang_luc_kenh_bot import ZALO_BOT_CAPABILITIES
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi
from pema.channels.zalo_bot.zalo_bot_api_types import (
    TRAN_KY_TU_MOT_TIN,
    ZaloBotUpdate,
    unwrap_webhook_payload,
)
from pema.channels.zalo_bot.zalo_bot_update_parser import doi_update_sang_parsed_message
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
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
from pema_contracts.errors import ErrorCode

_log = create_logger("kenh-bot")

WEBHOOK_SECRET_HEADER = "x-bot-api-secret-token"  # noqa: S105 - a header NAME, not a secret

TRAN_DANG_NHAP_MS = 10 * 60 * 1000
"""Ceiling on how long the "typing" indicator is kept, matching ``DEFAULT_MAX_DURATION_MS`` of the personal
channel. A safety net for a caller that forgets to call the stop function."""


def _swallow(task: asyncio.Future[object]) -> None:
    if task.cancelled():
        return
    err = task.exception()
    if err is not None:
        _log.debug("Bắn 'đang nhập' thất bại - bỏ qua", err=err)


class ZaloBotChannel:
    def __init__(
        self,
        client: BotApiClient,
        account_id: str,
        *,
        webhook_secret: str | None = None,
        typing_refresh_ms: Callable[[], int] | None = None,
    ) -> None:
        self._client = client
        self._account_id = account_id
        self._webhook_secret = webhook_secret
        # A function, so an edit of ``TYPING_REFRESH_MS`` on the Settings page applies at the next typing
        # start.
        self._typing_refresh_ms = typing_refresh_ms or (lambda: get_tuning_int("TYPING_REFRESH_MS"))

    # ------------------------------------------------------------------ ChannelPort
    @property
    def kind(self) -> ChannelKind:
        return ChannelKind.ZALO_BOT

    @property
    def account_id(self) -> str:
        return self._account_id

    def capabilities(self) -> ChannelCapabilities:
        return ZALO_BOT_CAPABILITIES

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Constant-time check of the secret header; ``False`` on any mismatch, and when NO secret is
        configured (fail closed: an unconfigured account must not accept anonymous updates)."""
        if not self._webhook_secret:
            return False
        received = ""
        for name, value in headers.items():
            if name.lower() == WEBHOOK_SECRET_HEADER:
                received = value
                break
        return hmac.compare_digest(received.encode("utf-8"), self._webhook_secret.encode("utf-8"))

    def parse_inbound(self, update: Mapping[str, object]) -> InboundMessage | None:
        try:
            parsed = ZaloBotUpdate.model_validate(unwrap_webhook_payload(update))
        except ValidationError:
            return None
        return doi_update_sang_parsed_message(self._account_id, parsed)

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
        # Send PLAIN TEXT (``parse_mode`` None), not asking the server to build markdown.
        #
        # The reason is not obvious: the text reaching here ALREADY has no markdown. The reply path runs the
        # formatter first and ``markdown_sang_style_zalo`` STRIPS the marks into a ``Style[]`` (measured:
        # "**Bảng giá** đây anh" becomes "Bảng giá đây anh" + 1 style). So asking the server to build markdown
        # at this step can only REMOVE characters (a stray ``_`` ``*`` ``[`` left in a file name or a source
        # label).
        #
        # Measured on the real API: both ``parse_mode: "markdown"`` and ``None`` are accepted for a string
        # with a lone ``_`` and ``[``, no 400 risk. ``None`` is chosen for the reason above, not for fear of
        # errors.
        #
        # Accepted consequence: the bot channel has NO bold/italic.
        #
        # ``styles`` (a field of the personal-account library, the Bot API does not understand it) and
        # ``quote`` (the Bot API has no quoting; measured: no method) are NOT sent. Dropped quietly instead of
        # raising: both are decoration, losing them still answers. ``proactive`` is the caller's marker; the
        # guard that enforces cap/window/kill switch is package S's and has already decided when this is
        # called.
        if not text.strip():
            return SendResult(
                status=SendStatus.REJECTED, error_code=ErrorCode.VALIDATION_FAILED, detail="empty text"
            )
        if len(text) > TRAN_KY_TU_MOT_TIN:
            # The server REFUSES the whole message (measured: 2001 characters rejected), so refuse here with a
            # clear code instead of losing the reply; splitting is ``send_reply_in_parts``' job.
            return SendResult(
                status=SendStatus.REJECTED,
                error_code=ErrorCode.PAYLOAD_TOO_LARGE,
                detail="text over 2000 characters",
            )
        try:
            sent = await self._client.send_message(thread_id, text, None)
        except LoiZaloBotApi as err:
            _log.warning(
                "Gửi tin qua Bot API thất bại",
                account_id=self._account_id,
                method=err.method,
                http_status=err.http_status,
                zalo_code=err.ma_loi,
            )
            return SendResult(
                status=SendStatus.REJECTED, error_code=_error_code_of(err), detail=str(err)[:200]
            )
        return SendResult(
            status=SendStatus.SENT,
            external_message_id=sent.message_id,
            sent_at=_sent_at(sent.date),
        )

    # ------------------------------------------------------------------ TypingChannel
    def start_typing(self, thread_id: str, thread_kind: ThreadKind) -> Callable[[], None]:
        """``batDangNhap``: start the "typing" indicator and return the function that stops it.

        A loop of its own instead of the personal channel's ``startTypingIndicator``: that one takes
        ``(threadId, threadType)`` in the zca-js shape. But the two safety nets of it are KEPT, because
        without them the damage is worse here:

        - A time ceiling: a caller that forgets the stop function makes this loop fire forever. Every beat is
          a REAL HTTP POST to the very nginx measured to answer 429 when asked in a burst; unlike the personal
          channel, where every beat is only a socket event.
        - Catch SYNCHRONOUS errors: if ``send_chat_action`` raises at once (before it returns a coroutine) a
          ``.catch`` cannot help, the error escapes the timer callback and becomes uncaught."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _log.debug("Không có event loop - bỏ qua dấu 'đang nhập'", thread_id=thread_id)
            return lambda: None

        started = loop.time()
        state: dict[str, object] = {"stopped": False, "timer": None}

        def dung() -> None:
            state["stopped"] = True
            timer = state["timer"]
            if isinstance(timer, asyncio.TimerHandle):
                timer.cancel()

        def ban_mot() -> None:
            if state["stopped"]:
                return
            if (loop.time() - started) * 1000 > TRAN_DANG_NHAP_MS:
                _log.debug("Dấu 'đang nhập' chạm trần thời gian - tự tắt", thread_id=thread_id)
                dung()
                return
            try:
                task = asyncio.ensure_future(self._client.send_chat_action(thread_id))
                task.add_done_callback(_swallow)
            except Exception as err:
                _log.debug("Bắn 'đang nhập' ném đồng bộ - bỏ qua", err=err, thread_id=thread_id)
            state["timer"] = loop.call_later(self._typing_refresh_ms() / 1000, ban_mot)

        ban_mot()
        return dung


def _error_code_of(err: LoiZaloBotApi) -> ErrorCode:
    codes = {err.http_status, _as_int(err.ma_loi)}
    if 429 in codes:
        return ErrorCode.RATE_LIMITED
    if 403 in codes:
        return ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE
    return ErrorCode.CHANNEL_UNAVAILABLE


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return None


def _sent_at(date_ms: float | None) -> datetime:
    if date_ms is not None and date_ms > 0:
        try:
            return datetime.fromtimestamp(date_ms / 1000, UTC)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(UTC)
