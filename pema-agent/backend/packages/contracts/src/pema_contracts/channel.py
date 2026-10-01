"""``ChannelPort``: the only way the rest of the system talks to a messaging channel.

Derived from the channel seam of zalo-agent: ``KenhLuot`` (src/zalo/kenh-luot.ts), ``ReplyTarget`` /
``DoanCanGui`` (src/zalo/send-reply-in-parts.ts), ``ParsedMessage`` (src/zalo/zalo-message-parser.ts)
and the capability table of the Bot channel (src/zalo-bot/nang-luc-kenh-bot.ts). One ``ChannelPort``
instance is bound to ONE account (``account_id``) of ONE kind:

* ``zalo_bot``      Zalo Bot API, official, text + photo-by-URL only. Package C1.
* ``zalo_personal`` personal account through the zca-js Node bridge. Package C2.
* ``zalo_oa``       stub only in AI01 (PLAN-AI01 section 8): every call raises ``NotImplementedError``.

Design rules:

* ``capabilities``, ``verify_webhook`` and ``parse_inbound`` are pure and synchronous.
* ``send_text`` sends ONE already split part (splitting, markdown to styles, sanitising and the
  per-thread rate limiter live in the channel middleware, not here). It never raises for a guard:
  it answers with a rejected ``SendResult`` carrying an ``ErrorCode``.
* Optional abilities are separate ``Protocol``s (``TypingChannel``, ``ReadReceiptChannel``,
  ``ReactionChannel``, ``MediaChannel``, ``GroupChannel``). A channel that lacks one simply does not
  implement it, like zalo-agent leaves ``baoDaXem`` / ``tuThaCamXuc`` undefined on the Bot channel
  instead of stubbing a function that throws. Callers test ``isinstance(channel, TypingChannel)``.
* Which tools a channel cannot run is data (``ChannelCapabilities.blocked_tools``), the port of
  ``TOOL_KHONG_CHAY_TREN_BOT``: blocked tools never reach the model schema.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, JsonObject, VnDatetime
from pema_contracts.errors import ErrorCode

ZALO_BOT_MAX_TEXT_CHARS = 2000
"""Hard server limit of the Bot API (measured by zalo-agent: 2001 chars is rejected). TRAN_KY_TU_MOT_TIN."""

ZALO_PERSONAL_DEFAULT_MAX_TEXT_CHARS = 2000
"""Default ``ZALO_MAX_MESSAGE_CHARS``; tunable up to 4000 on the personal channel."""

ZALO_PERSONAL_DEFAULT_DAILY_CAP = 10
"""Default of ``SCHEDULER_MAX_PROACTIVE_PER_DAY`` (zalo-agent: 10 proactive messages per day). The key is
(account, thread, day) in ``staff_assistant`` and (patient, account, day) in ``patient_channel``. It is a
per-conversation cap, tunable 1..100; it is not an account-wide quota."""


class ChannelKind(StrEnum):
    ZALO_BOT = "zalo_bot"
    ZALO_PERSONAL = "zalo_personal"
    ZALO_OA = "zalo_oa"


class ThreadKind(StrEnum):
    """zca-js ``ThreadType``: 0 = direct, 1 = group. Stored as int in ``agent.threads.thread_type``."""

    USER = "user"
    GROUP = "group"


class InboundKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    STICKER = "sticker"
    VOICE = "voice"
    FILE = "file"
    UNSUPPORTED = "unsupported"


class InboundImage(ApiModel):
    url: str
    local_path: str | None = Field(
        default=None, description="Path inside the media store, set after the image is persisted."
    )


class TextStyle(ApiModel):
    """One rich-text span (zca-js ``Style``: ``start``, ``len``, ``st``). Offsets are UTF-16 units."""

    start: int = Field(ge=0)
    length: int = Field(ge=1)
    style: str = Field(description="zca-js style code, e.g. 'b', 'i', 'u', 'c_db342e', 'f_18'.")


class QuoteRef(ApiModel):
    """Message to quote when replying (groups only, see reply-quote.ts). Only the first part carries it."""

    msg_id: str
    cli_msg_id: str
    sender_id: str
    raw: JsonObject = Field(default_factory=dict, description="Channel raw data needed to build the quote.")


class ChannelCapabilities(ApiModel):
    channel: ChannelKind
    supports_inbound: bool = True
    can_send_proactive: bool = Field(
        description="May the system message a patient with no recent inbound message from them?"
    )
    daily_cap: int | None = Field(
        default=None,
        ge=0,
        description="Proactive messages per day per (account, thread). None = the channel imposes none.",
    )
    requires_friend: bool = Field(
        default=False, description="Recipient must be a friend / have an existing conversation."
    )
    max_text_length: int = Field(default=ZALO_BOT_MAX_TEXT_CHARS, ge=1)
    supports_formatting: bool = Field(
        default=True,
        description="Can carry TextStyle spans on the wire (KenhLuot.mangDinhDang). False: markers are "
        "stripped and the spans dropped; they must not count against the byte budget when splitting.",
    )
    supports_quote: bool = True
    supports_typing_indicator: bool = False
    supports_read_receipt: bool = False
    supports_reactions: bool = False
    supports_send_image: bool = False
    supports_send_file: bool = False
    supports_send_video: bool = False
    supports_group_info: bool = False
    supports_tag_member: bool = False
    min_gap_seconds: int = Field(default=0, ge=0, description="Random gap lower bound between sends.")
    max_gap_seconds: int = Field(default=0, ge=0, description="Random gap upper bound between sends.")
    send_window_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    send_window_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    blocked_tools: dict[str, str] = Field(
        default_factory=dict,
        description="Tool key -> short hint shown on the Tools page. Port of TOOL_KHONG_CHAY_TREN_BOT.",
    )
    persona_rule: str | None = Field(
        default=None,
        description="Line appended to the persona when the turn runs on this channel "
        "(LUAT_PERSONA_KENH_BOT), so the model explains platform limits instead of failing silently.",
    )


class InboundMessage(ApiModel):
    """A normalised inbound message. Port of ``ParsedMessage`` plus the de-duplication key."""

    channel: ChannelKind
    account_id: str
    update_id: str = Field(description="Channel-unique id used to drop duplicate deliveries.")
    kind: InboundKind = InboundKind.TEXT
    thread_id: str
    thread_kind: ThreadKind = ThreadKind.USER
    is_group: bool = False
    sender_id: str = Field(description="Opaque channel user id. An identifier, not a name.")
    sender_name: str = Field(default="", description="Display name from the channel. PII: never logged.")
    text: str = Field(default="", max_length=20000)
    images: list[InboundImage] = Field(default_factory=list[InboundImage])
    msg_id: str
    cli_msg_id: str = ""
    is_self: bool = False
    mentions_me: bool = False
    sent_at: VnDatetime = Field(description="When the sender pressed send (not when we received it).")
    history_row_id: int | None = Field(
        default=None, description="Row id in agent.history, stamped when the message is recorded."
    )
    raw: JsonObject = Field(default_factory=dict, description="Original channel payload (for quotes).")


class SendStatus(StrEnum):
    SENT = "sent"
    QUEUED = "queued"
    REJECTED = "rejected"


class SendResult(ApiModel):
    status: SendStatus
    external_message_id: str | None = None
    sent_at: VnDatetime | None = None
    error_code: ErrorCode | None = Field(
        default=None, description="Set when rejected (cap reached, kill switch, not friend, ...)."
    )
    detail: str | None = Field(default=None, description="Short diagnostic. No PII, no message text.")


@runtime_checkable
class ChannelPort(Protocol):
    """Contract implemented by ``pema.channels.zalo_bot`` and ``pema.channels.zalo_personal``."""

    @property
    def kind(self) -> ChannelKind: ...

    @property
    def account_id(self) -> str: ...

    def capabilities(self) -> ChannelCapabilities:
        """Static description of what the channel allows. Safe to call on every turn."""
        ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Check the webhook secret/signature. Constant-time; ``False`` on any mismatch."""
        ...

    def parse_inbound(self, update: Mapping[str, object]) -> InboundMessage | None:
        """Normalise a raw update. ``None`` for updates that are not user messages (acks, own echoes)."""
        ...

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
        """Send ONE part. ``proactive=True`` marks a message not triggered by a recent inbound message:
        the proactive guard (daily cap, window, gap, kill switch) applies and a block is a rejected
        ``SendResult``, never an exception. The caller already holds the human approval the policy
        profile demands."""
        ...


@runtime_checkable
class TypingChannel(Protocol):
    """``KenhLuot.batDangNhap``: start the typing indicator, get back the function that stops it."""

    def start_typing(self, thread_id: str, thread_kind: ThreadKind) -> Callable[[], None]: ...


@runtime_checkable
class ReadReceiptChannel(Protocol):
    """``KenhLuot.baoDaXem``: mark a batch as seen. Absent on the Bot channel."""

    async def mark_seen(self, messages: Sequence[InboundMessage]) -> None: ...


@runtime_checkable
class ReactionChannel(Protocol):
    """``add_reaction`` tool and ``autoReactEnabled``. Absent on the Bot channel."""

    async def react(self, message: InboundMessage, icon: str) -> SendResult: ...


@runtime_checkable
class MediaChannel(Protocol):
    """Outbound files, photos and video (zalo-agent ``send_file``, ``create_image``, ``tai_video``).

    Implemented by ``zalo_personal`` only. The Bot API takes photos by public URL and has no file or
    video method. Disabled in the ``patient_channel`` profile regardless of capability.
    """

    async def send_image(
        self, thread_id: str, thread_kind: ThreadKind, data: bytes, caption: str
    ) -> SendResult: ...

    async def send_file(
        self, thread_id: str, thread_kind: ThreadKind, filename: str, data: bytes, caption: str
    ) -> SendResult: ...

    async def send_video(
        self, thread_id: str, thread_kind: ThreadKind, url: str, caption: str
    ) -> SendResult: ...


@runtime_checkable
class GroupChannel(Protocol):
    """``get_group_info`` and ``tag_member`` tools. Personal channel only."""

    async def get_group_info(self, thread_id: str) -> JsonObject: ...

    async def tag_member(self, thread_id: str, member_id: str, text: str) -> SendResult: ...


class ChannelRegistry(Protocol):
    """Which channels are RUNNING right now (``getRunningAccountKenh``). The scheduler and the tools ask it
    for the channel of an account; ``None`` means the account is not running (not logged in, stopped, bot
    without token): the scheduler then keeps the run slot and retries on the next tick.

    The implementation is ``pema.channels.registry.InMemoryChannelRegistry`` (package A, done): C1 and C2
    register their channels when an account starts and unregister when it stops.
    """

    def get_running(self, clinic_id: UUID, account_id: str) -> ChannelPort | None: ...

    def list_running(self, clinic_id: UUID) -> list[ChannelPort]: ...
