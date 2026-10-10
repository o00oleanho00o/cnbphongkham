# ported from: src/conversation/contact-store.ts, src/zalo/incoming-message-router.ts (group names)
"""The address book the plugin collects by itself: everyone who wrote to an account (even people the account
does not answer, so the admin sees who tried) and the names of the groups a personal account is in.

Kept in ``ctx.storage``: ``contact:<account>:<user>`` and ``group:<account>:<thread>``. Deleting a contact
touches nothing else; when the person writes again the row comes back, counted from one.

Known limit: a listing reads at most ``MAX_LIST`` records of the storage, so a book past that size shows only
its first ``MAX_LIST`` entries in key order (sorting and search happen after).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any, Final, cast

from pydantic import BaseModel

from agent_app.plugins import PluginStorage

from .models import ContactOut, GroupOut

CONTACT: Final = "contact:"
GROUP: Final = "group:"


class _Contact(BaseModel):
    display_name: str = ""
    first_seen: datetime
    last_seen: datetime
    message_count: int = 0


def _prefix(kind: str, account_id: str | None) -> str:
    return kind if not account_id else f"{kind}{account_id}:"


def _split(key: str, kind: str) -> tuple[str, str]:
    account_id, _, item = key.removeprefix(kind).partition(":")
    return account_id, item


class ContactBook:
    def __init__(self, storage: PluginStorage) -> None:
        self._storage = storage

    async def record(self, account_id: str, user_id: str, display_name: str, now: datetime) -> None:
        """One message heard from this person; a blank name keeps the one already known."""
        if not user_id:
            return
        key = f"{CONTACT}{account_id}:{user_id}"
        found = await self._storage.get(key)
        if isinstance(found, Mapping):
            contact = _Contact.model_validate(found)
            contact.last_seen = now
            contact.message_count += 1
            contact.display_name = display_name or contact.display_name
        else:
            contact = _Contact(display_name=display_name, first_seen=now, last_seen=now, message_count=1)
        await self._storage.put(key, contact.model_dump(mode="json"))

    async def delete(self, account_id: str, user_id: str) -> bool:
        return await self._storage.delete(f"{CONTACT}{account_id}:{user_id}")

    async def names(self, account_id: str, user_ids: Collection[str]) -> dict[str, str]:
        """The known display names of these people (one read of the account's book); people without a name or
        not in the book are left out."""
        wanted = set(user_ids)
        found: dict[str, str] = {}
        for key, value in await self._storage.list(_prefix(CONTACT, account_id)):
            _, user_id = _split(key, CONTACT)
            if user_id not in wanted:
                continue
            name = _Contact.model_validate(value).display_name
            if name:
                found[user_id] = name
        return found

    async def list(
        self, *, account_id: str | None = None, query: str = "", limit: int = 50, offset: int = 0
    ) -> list[ContactOut]:
        """Most recently heard first; ``query`` matches the name or the id, ignoring case."""
        needle = query.strip().casefold()
        found: list[ContactOut] = []
        for key, value in await self._storage.list(_prefix(CONTACT, account_id)):
            owner, user_id = _split(key, CONTACT)
            contact = _Contact.model_validate(value)
            if needle and needle not in contact.display_name.casefold() and needle not in user_id.casefold():
                continue
            found.append(ContactOut(account_id=owner, user_id=user_id, **contact.model_dump()))
        found.sort(key=lambda c: c.last_seen, reverse=True)
        return found[offset : offset + limit]


class GroupNames:
    def __init__(self, storage: PluginStorage) -> None:
        self._storage = storage

    async def get(self, account_id: str, thread_id: str) -> str | None:
        value = await self._storage.get(f"{GROUP}{account_id}:{thread_id}")
        return value if isinstance(value, str) else None

    async def set(self, account_id: str, thread_id: str, name: str) -> None:
        await self._storage.put(f"{GROUP}{account_id}:{thread_id}", name)

    async def list(self, account_id: str | None = None) -> list[GroupOut]:
        out: list[GroupOut] = []
        for key, value in await self._storage.list(_prefix(GROUP, account_id)):
            owner, thread_id = _split(key, GROUP)
            out.append(GroupOut(account_id=owner, thread_id=thread_id, name=str(value)))
        return out


def group_name(info: Mapping[str, Any], thread_id: str) -> str | None:
    """The name in a zca-js ``getGroupInfo`` answer (``gridInfoMap[<id>].name``)."""
    grid = info.get("gridInfoMap")
    entry = cast(Mapping[str, Any], grid).get(thread_id) if isinstance(grid, Mapping) else None
    name = cast(Mapping[str, Any], entry).get("name") if isinstance(entry, Mapping) else None
    name = name or info.get("name")
    return (name.strip() or None) if isinstance(name, str) else None
