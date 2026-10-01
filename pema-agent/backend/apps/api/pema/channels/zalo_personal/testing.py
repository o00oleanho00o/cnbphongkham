"""Test doubles of the personal-account channel (import in tests only, like ``pema_contracts.testing``).

``FakeZaloApi`` stands in for the zca-js ``API`` object: it records every call and never touches a network.
The suite runs with ``--import-mode=importlib`` and no ``tests`` package, so shared fakes live in the package.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pema.channels.zalo_personal.bridge_client import ReceiptParams, ZaloApi, ZaloBridgeError
from pema_contracts.channel import QuoteRef, TextStyle, ThreadKind
from pema_contracts.common import JsonObject


@dataclass
class SentMessage:
    text: str
    thread_id: str
    thread_type: ThreadKind
    styles: tuple[TextStyle, ...]
    quote: QuoteRef | None
    proactive: bool
    mentions: tuple[JsonObject, ...] = ()


@dataclass
class FakeZaloApi:
    """Records every call. ``fail_send_with`` makes ``send_message`` raise (one entry per call, in order)."""

    account: str = "acc-1"
    own_id: str = "self-1"
    sent: list[SentMessage] = field(default_factory=list[SentMessage])
    typing: list[tuple[str, ThreadKind]] = field(default_factory=list[tuple[str, ThreadKind]])
    delivered: list[tuple[bool, tuple[ReceiptParams, ...], ThreadKind]] = field(
        default_factory=list[tuple[bool, tuple[ReceiptParams, ...], ThreadKind]]
    )
    seen: list[tuple[tuple[ReceiptParams, ...], ThreadKind]] = field(
        default_factory=list[tuple[tuple[ReceiptParams, ...], ThreadKind]]
    )
    reactions: list[tuple[str, str, str, ThreadKind]] = field(
        default_factory=list[tuple[str, str, str, ThreadKind]]
    )
    user_info: dict[str, JsonObject] = field(default_factory=dict[str, JsonObject])
    friends: list[JsonObject] = field(default_factory=list[JsonObject])
    accepted: list[str] = field(default_factory=list[str])
    rejected: list[str] = field(default_factory=list[str])
    fail_send_with: list[ZaloBridgeError] = field(default_factory=list[ZaloBridgeError])
    fail_accept_for: set[str] = field(default_factory=set[str])

    @property
    def account_id(self) -> str:
        return self.account

    def get_own_id(self) -> str:
        return self.own_id

    async def send_message(
        self,
        *,
        text: str,
        thread_id: str,
        thread_type: ThreadKind,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        mentions: Sequence[JsonObject] = (),
        proactive: bool = False,
    ) -> JsonObject:
        if self.fail_send_with:
            raise self.fail_send_with.pop(0)
        self.sent.append(
            SentMessage(text, thread_id, thread_type, tuple(styles), quote, proactive, tuple(mentions))
        )
        return {"msg_id": f"sent-{len(self.sent)}"}

    async def send_typing_event(self, thread_id: str, thread_type: ThreadKind) -> None:
        self.typing.append((thread_id, thread_type))

    async def send_delivered_event(
        self, is_seen: bool, params: Sequence[ReceiptParams], thread_type: ThreadKind
    ) -> None:
        self.delivered.append((is_seen, tuple(params), thread_type))

    async def send_seen_event(self, params: Sequence[ReceiptParams], thread_type: ThreadKind) -> None:
        self.seen.append((tuple(params), thread_type))

    async def add_reaction(
        self, icon_key: str, *, msg_id: str, cli_msg_id: str, thread_id: str, thread_type: ThreadKind
    ) -> None:
        self.reactions.append((icon_key, msg_id, thread_id, thread_type))

    async def get_user_info(self, uid: str) -> JsonObject:
        return self.user_info.get(uid, {"changed_profiles": {}})

    async def get_all_friends(self) -> list[JsonObject]:
        return list(self.friends)

    async def accept_friend_request(self, uid: str) -> None:
        if uid in self.fail_accept_for:
            raise ZaloBridgeError("zalo_rejected", "synthetic failure", code=1)
        self.accepted.append(uid)

    async def reject_friend_request(self, uid: str) -> None:
        self.rejected.append(uid)

    async def get_group_info(self, thread_id: str) -> JsonObject:
        return {"gridInfoMap": {thread_id: {"name": "Synthetic group"}}}

    async def send_attachment(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        filename: str,
        data: bytes,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return {"msg_id": "att-1"}

    async def send_video(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        video_url: str,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return {"msg_id": "vid-1"}


_check: ZaloApi = FakeZaloApi()
