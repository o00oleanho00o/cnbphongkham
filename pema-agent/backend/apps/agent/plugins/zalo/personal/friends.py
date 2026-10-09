# ported from: src/conversation/friend-request-store.ts, src/zalo/friend-event-handler.ts,
# src/zalo/friend-auto-accept-sweep.ts
"""Friend requests to a personal account: the ones waiting, kept from the bridge's ``friend_event`` until
someone (the admin, or the auto-accept round) decides, and the round itself.

The bridge normalises zca-js's ``FriendEvent`` into ``{"kind", "thread_id", "is_self", "data"}``: a request
has ``data.fromUid`` / ``data.message``; a withdrawn or refused request has ``data.fromUid``; for ``add`` the
new friend is the thread id. Kept in ``ctx.storage`` as ``friend-request:<account>:<uid>``.

A request is stored first and enriched with the sender's name afterwards, and the enrichment only updates:
``getUserInfo`` can take seconds, and an ``add`` arriving meanwhile must not be followed by a ghost row for
someone who is already a friend. A row goes away only after Zalo took the decision, so a failed one is tried
again.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final, Protocol, cast

from pydantic import BaseModel

from agent_app.plugins import PluginStorage

from ..models import AccountConfig, FriendRequestOut
from .client import ZaloBridgeError

REQUEST: Final = "friend-request:"
SWEEP_EVERY_S: Final = 30.0

logger = logging.getLogger(__name__)

UserInfo = Callable[[str], Awaitable[Mapping[str, Any]]]


class _Request(BaseModel):
    message: str = ""
    sender_name: str | None = None
    avatar_url: str | None = None
    received_at: datetime


class FriendRequests:
    def __init__(self, storage: PluginStorage) -> None:
        self._storage = storage

    async def put(self, account_id: str, from_uid: str, message: str, now: datetime) -> None:
        """A sender asking again replaces the row (and its waiting time)."""
        row = _Request(message=message, received_at=now)
        await self._storage.put(_key(account_id, from_uid), row.model_dump(mode="json"))

    async def set_profile(
        self, account_id: str, from_uid: str, sender_name: str | None, avatar_url: str | None
    ) -> None:
        """Only an existing row: one resolved meanwhile stays gone."""
        found = await self._storage.get(_key(account_id, from_uid))
        if not isinstance(found, Mapping):
            return
        row = _Request.model_validate(found)
        row.sender_name, row.avatar_url = sender_name, avatar_url
        await self._storage.put(_key(account_id, from_uid), row.model_dump(mode="json"))

    async def delete(self, account_id: str, from_uid: str) -> bool:
        return await self._storage.delete(_key(account_id, from_uid))

    async def list(self, account_id: str) -> list[FriendRequestOut]:
        """Newest first."""
        prefix = _key(account_id, "")
        rows = [
            FriendRequestOut(from_uid=key.removeprefix(prefix), **_Request.model_validate(value).model_dump())
            for key, value in await self._storage.list(prefix)
        ]
        return sorted(rows, key=lambda r: r.received_at, reverse=True)

    async def waiting_since(self, account_id: str, cutoff: datetime) -> list[FriendRequestOut]:
        """The requests received at ``cutoff`` or before, oldest first."""
        return sorted(
            (r for r in await self.list(account_id) if r.received_at <= cutoff), key=lambda r: r.received_at
        )


def _key(account_id: str, from_uid: str) -> str:
    return f"{REQUEST}{account_id}:{from_uid}"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _profile(info: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Name and avatar from a ``getUserInfo`` answer; None for what is not there."""
    profiles = info.get("changed_profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        return None, None
    first = next(iter(cast(Mapping[str, Any], profiles).values()))
    if not isinstance(first, Mapping):
        return None, None
    profile = cast(Mapping[str, Any], first)
    return _text(profile.get("displayName")) or _text(profile.get("zaloName")), _text(profile.get("avatar"))


async def handle_friend_event(
    requests: FriendRequests,
    account_id: str,
    event: Mapping[str, Any],
    *,
    user_info: UserInfo | None,
    now: datetime,
) -> None:
    """One ``friend_event`` of the bridge. Logs ids and kinds only."""
    kind = event.get("kind")
    raw = event.get("data")
    data: Mapping[str, Any] = cast(Mapping[str, Any], raw) if isinstance(raw, Mapping) else {}
    if kind == "request":
        from_uid = _text(data.get("fromUid"))
        if event.get("is_self") or from_uid is None:
            return  # a request the account sent
        await requests.put(account_id, from_uid, _text(data.get("message")) or "", now)
        logger.info("personal account %s has a new friend request", account_id)
        if user_info is None:
            return
        try:
            name, avatar = _profile(await user_info(from_uid))
        except ZaloBridgeError as err:  # the request is kept with its id only
            logger.info("personal account %s: no profile for a friend request (%s)", account_id, err.kind)
            return
        if name or avatar:
            await requests.set_profile(account_id, from_uid, name, avatar)
        return
    if kind == "add":
        resolved = _text(event.get("thread_id"))
    elif kind in ("reject_request", "undo_request"):
        resolved = _text(data.get("fromUid"))
    else:
        resolved = None
    if resolved is not None:
        await requests.delete(account_id, resolved)
    else:
        logger.debug("personal account %s: friend event %s needs nothing", account_id, kind)


class AcceptsFriends(Protocol):
    async def accept_friend_request(self, uid: str) -> None: ...


async def auto_accept_round(
    requests: FriendRequests, running: Iterable[tuple[AccountConfig, AcceptsFriends]], now: datetime
) -> None:
    """Accepts, for every running account that wants it, the requests that waited its delay. One failure
    does not stop the others; its row stays for the next round. An admin deciding the same request in the
    same seconds makes one of the two calls fail harmlessly (already a friend)."""
    for account, api in running:
        if not account.auto_accept_friends:
            continue
        cutoff = now - timedelta(minutes=account.auto_accept_friend_delay_minutes)
        for request in await requests.waiting_since(account.id, cutoff):
            try:
                await api.accept_friend_request(request.from_uid)
            except ZaloBridgeError as err:
                logger.warning(
                    "personal account %s: auto-accept failed (%s); tried again next round",
                    account.id,
                    err.kind,
                )
                continue
            await requests.delete(account.id, request.from_uid)
            logger.info("personal account %s accepted a friend request by itself", account.id)
