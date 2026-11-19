"""Where conversations and their messages are kept: Postgres (the plugin's own ``cv_`` tables, scoped by
tenant and agent) or process memory (tests, an agent run without a database).

A message is kept once: the platform's id of it, within its conversation, is unique, so hearing it twice
(a webhook retried, a channel restarted) changes nothing."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Text

from .models import Conversation, Message, NewMessage, Person, Role


class ConversationStore(Protocol):
    async def add(self, message: NewMessage) -> bool:
        """Keeps the message (and its conversation, made when new); False when it was kept before or its
        conversation is switched off."""
        ...

    async def conversations(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Newest first, and how many match; ``query`` is looked for in the title and the messages."""
        ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def messages(self, conversation_id: str, *, limit: int) -> list[Message]:
        """The latest ``limit`` messages, oldest first."""
        ...

    async def set_excluded(self, conversation_id: str, excluded: bool) -> bool: ...

    async def delete(self, conversation_id: str) -> bool: ...

    async def delete_many(self, conversation_ids: Sequence[str]) -> int:
        """Deletes these conversations with their messages; how many existed."""
        ...

    async def purge_before(self, cutoff: datetime) -> int:
        """Deletes the messages older than ``cutoff`` and the conversations left empty; how many messages."""
        ...

    async def people(self, channel: str) -> list[Person]:
        """Everyone who wrote in the channel (not the agent), most active first."""
        ...

    async def relabel(self, channel: str, sender_ids: Collection[str], role: Role) -> int:
        """Gives these people's earlier messages in the channel the role they now have; how many changed."""
        ...

    async def to_cut(self, *, idle_before: datetime, limit: int) -> list[Conversation]:
        """Conversations with messages not yet looked at for episodes whose last message is not newer than
        ``idle_before`` (the chat has gone quiet), oldest first."""
        ...

    async def uncut_messages(
        self, conversation_ids: Sequence[str], *, limit: int
    ) -> dict[str, list[Message]]:
        """For each conversation, its messages not yet looked at for episodes, in the order they were kept (at
        most ``limit`` in all)."""
        ...

    async def mark_cut(self, marks: Mapping[str, int]) -> None:
        """Conversation id -> the last message looked at for episodes."""
        ...


def _like(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}
        self._cut: dict[str, int] = {}
        self._seq = 0

    async def add(self, message: NewMessage) -> bool:
        found = self._conversations.get(message.conversation_id)
        if found is not None and found.excluded:
            return False
        rows = self._messages.setdefault(message.conversation_id, [])
        if any(r.message_id == message.message_id for r in rows):
            return False
        self._seq += 1
        rows.append(
            Message(
                self._seq,
                message.conversation_id,
                message.message_id,
                message.sender_id,
                message.sender_name,
                message.role,
                message.origin,
                message.at,
                message.text,
                message.answered,
            )
        )
        if found is None:
            self._conversations[message.conversation_id] = Conversation(
                message.conversation_id,
                message.channel,
                message.external_id,
                message.is_group,
                message.title_hint,
                False,
                1,
                message.at,
                message.at,
            )
        else:
            self._conversations[found.id] = replace(
                found,
                title=found.title or message.title_hint,
                message_count=found.message_count + 1,
                first_at=min(found.first_at, message.at),
                last_at=max(found.last_at, message.at),
            )
        return True

    async def conversations(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        needle = query.strip().lower()

        def matches(c: Conversation) -> bool:
            if channel is not None and c.channel != channel:
                return False
            if not needle:
                return True
            return needle in c.title.lower() or any(needle in m.text.lower() for m in self._messages[c.id])

        found = sorted(
            (c for c in self._conversations.values() if matches(c)), key=lambda c: c.last_at, reverse=True
        )
        return found[offset : offset + limit], len(found)

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    async def messages(self, conversation_id: str, *, limit: int) -> list[Message]:
        rows = sorted(self._messages.get(conversation_id, []), key=lambda m: (m.at, m.seq))
        return rows[-limit:]

    async def set_excluded(self, conversation_id: str, excluded: bool) -> bool:
        found = self._conversations.get(conversation_id)
        if found is None:
            return False
        self._conversations[found.id] = replace(found, excluded=excluded)
        return True

    async def delete(self, conversation_id: str) -> bool:
        self._messages.pop(conversation_id, None)
        return self._conversations.pop(conversation_id, None) is not None

    async def delete_many(self, conversation_ids: Sequence[str]) -> int:
        for conversation_id in conversation_ids:
            self._messages.pop(conversation_id, None)
        return sum(self._conversations.pop(i, None) is not None for i in set(conversation_ids))

    async def purge_before(self, cutoff: datetime) -> int:
        gone = 0
        for conversation_id in list(self._conversations):
            rows = self._messages.get(conversation_id, [])
            kept = [m for m in rows if m.at >= cutoff]
            gone += len(rows) - len(kept)
            # An excluded conversation stays, even empty: dropping it would forget the admin's choice.
            if not kept and not self._conversations[conversation_id].excluded:
                self._conversations.pop(conversation_id, None)
                self._messages.pop(conversation_id, None)
                continue
            self._messages[conversation_id] = kept
            if not kept:
                continue
            self._conversations[conversation_id] = replace(
                self._conversations[conversation_id],
                message_count=len(kept),
                first_at=min(m.at for m in kept),
                last_at=max(m.at for m in kept),
            )
        return gone

    async def people(self, channel: str) -> list[Person]:
        latest: dict[str, Message] = {}
        counts: Counter[str] = Counter()
        for conversation in self._conversations.values():
            if conversation.channel != channel:
                continue
            for m in self._messages.get(conversation.id, []):
                if m.origin != "inbound":
                    continue
                counts[m.sender_id] += 1
                if m.sender_id not in latest or latest[m.sender_id].at <= m.at:
                    latest[m.sender_id] = m
        people = [Person(i, m.sender_name, counts[i], m.role) for i, m in latest.items()]
        return sorted(people, key=lambda p: (-p.messages, p.sender_id))

    async def to_cut(self, *, idle_before: datetime, limit: int) -> list[Conversation]:
        waiting = [
            c
            for c in self._conversations.values()
            if c.last_at <= idle_before
            and any(m.seq > self._cut.get(c.id, 0) for m in self._messages.get(c.id, []))
        ]
        return sorted(waiting, key=lambda c: c.last_at)[:limit]

    async def uncut_messages(
        self, conversation_ids: Sequence[str], *, limit: int
    ) -> dict[str, list[Message]]:
        found = {
            cid: sorted(
                (m for m in self._messages.get(cid, []) if m.seq > self._cut.get(cid, 0)), key=lambda m: m.seq
            )
            for cid in conversation_ids
        }
        kept: dict[str, list[Message]] = {}
        room = limit
        for cid, rows in found.items():
            kept[cid] = rows[:room]
            room -= len(kept[cid])
        return kept

    async def mark_cut(self, marks: Mapping[str, int]) -> None:
        for cid, seq in marks.items():
            self._cut[cid] = max(self._cut.get(cid, 0), seq)

    async def relabel(self, channel: str, sender_ids: Collection[str], role: Role) -> int:
        changed = 0
        for conversation in self._conversations.values():
            if conversation.channel != channel:
                continue
            rows = self._messages.get(conversation.id, [])
            for index, m in enumerate(rows):
                if m.origin == "inbound" and m.sender_id in sender_ids and m.role != role:
                    rows[index] = replace(m, role=role)
                    changed += 1
        return changed


_UPSERT_CONVERSATION = text(
    "INSERT INTO agent_rt.cv_conversation (tenant_id, agent, id, channel, external_id, is_group, title, "
    "first_at, last_at) "
    "VALUES (:tenant_id, :agent, :id, :channel, :external_id, :is_group, :title, :at, :at) "
    "ON CONFLICT (tenant_id, agent, id) DO UPDATE SET "
    "title = CASE WHEN agent_rt.cv_conversation.title = '' THEN EXCLUDED.title "
    "ELSE agent_rt.cv_conversation.title END RETURNING excluded"
)
_INSERT_MESSAGE = text(
    "INSERT INTO agent_rt.cv_message (tenant_id, agent, conversation_id, external_id, sender_id, "
    "sender_name, role, origin, at, text, answered, meta) "
    "VALUES (:tenant_id, :agent, :id, :message_id, :sender_id, :sender_name, :role, :origin, :at, :text, "
    ":answered, CAST(:meta AS jsonb)) "
    "ON CONFLICT (tenant_id, agent, conversation_id, external_id) DO NOTHING RETURNING seq"
)
_TOUCH = text(
    "UPDATE agent_rt.cv_conversation SET message_count = message_count + 1, "
    "first_at = LEAST(first_at, :at), last_at = GREATEST(last_at, :at) "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_COLUMNS = "id, channel, external_id, is_group, title, excluded, message_count, first_at, last_at"
_FILTER = (
    "FROM agent_rt.cv_conversation c WHERE c.tenant_id = :tenant_id AND c.agent = :agent "
    "AND (CAST(:channel AS text) IS NULL OR c.channel = :channel) "
    "AND (CAST(:like AS text) IS NULL OR c.title ILIKE :like OR EXISTS ("
    "SELECT 1 FROM agent_rt.cv_message m WHERE m.tenant_id = c.tenant_id AND m.agent = c.agent "
    "AND m.conversation_id = c.id AND m.text ILIKE :like))"
)
_LIST = text(f"SELECT {_COLUMNS} {_FILTER} ORDER BY c.last_at DESC, c.id LIMIT :limit OFFSET :offset")
_COUNT = text(f"SELECT count(*) {_FILTER}")
_GET = text(
    f"SELECT {_COLUMNS} FROM agent_rt.cv_conversation "  # noqa: S608
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_MESSAGES = text(
    "SELECT seq, conversation_id, external_id, sender_id, sender_name, role, origin, at, text, answered "
    "FROM (SELECT * FROM agent_rt.cv_message WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND conversation_id = :id ORDER BY at DESC, seq DESC LIMIT :limit) latest ORDER BY at, seq"
)
_EXCLUDE = text(
    "UPDATE agent_rt.cv_conversation SET excluded = :excluded "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_DELETE = text(
    "DELETE FROM agent_rt.cv_conversation WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_DELETE_MANY = text(
    "DELETE FROM agent_rt.cv_conversation WHERE tenant_id = :tenant_id AND agent = :agent AND id = ANY(:ids)"
)
_PURGE = text(
    "DELETE FROM agent_rt.cv_message WHERE tenant_id = :tenant_id AND agent = :agent AND at < :cutoff"
)
_RECOUNT = text(
    "UPDATE agent_rt.cv_conversation c SET message_count = s.n, first_at = s.first_at, "
    "last_at = s.last_at "
    "FROM (SELECT conversation_id, count(*) AS n, min(at) AS first_at, max(at) AS last_at "
    "FROM agent_rt.cv_message WHERE tenant_id = :tenant_id AND agent = :agent GROUP BY conversation_id) s "
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.id = s.conversation_id "
    "AND c.message_count <> s.n"
)
_DROP_EMPTY = text(
    "DELETE FROM agent_rt.cv_conversation c WHERE c.tenant_id = :tenant_id AND c.agent = :agent "
    "AND NOT c.excluded AND NOT EXISTS (SELECT 1 FROM agent_rt.cv_message m WHERE m.tenant_id = c.tenant_id "
    "AND m.agent = c.agent AND m.conversation_id = c.id)"
)
_PEOPLE = text(
    "SELECT m.sender_id, "
    "(array_agg(m.sender_name ORDER BY m.at DESC) FILTER (WHERE m.sender_name <> ''))[1] AS name, "
    "count(*) AS messages, (array_agg(m.role ORDER BY m.at DESC))[1] AS role "
    "FROM agent_rt.cv_message m JOIN agent_rt.cv_conversation c ON c.tenant_id = m.tenant_id "
    "AND c.agent = m.agent AND c.id = m.conversation_id "
    "WHERE m.tenant_id = :tenant_id AND m.agent = :agent AND c.channel = :channel "
    "AND m.origin = 'inbound' "
    "GROUP BY m.sender_id ORDER BY messages DESC, m.sender_id"
)
_RELABEL = text(
    "UPDATE agent_rt.cv_message m SET role = :role FROM agent_rt.cv_conversation c "
    "WHERE m.tenant_id = :tenant_id AND m.agent = :agent AND c.tenant_id = m.tenant_id "
    "AND c.agent = m.agent AND c.id = m.conversation_id AND c.channel = :channel "
    "AND m.origin = 'inbound' AND m.sender_id = ANY(:sender_ids) AND m.role <> :role"
).bindparams(bindparam("sender_ids", type_=ARRAY(Text)))


_TO_CUT = text(
    f"SELECT {_COLUMNS} FROM agent_rt.cv_conversation c "  # noqa: S608
    "WHERE c.tenant_id = :tenant_id AND c.agent = :agent AND c.last_at <= :before "
    "AND EXISTS (SELECT 1 FROM agent_rt.cv_message m WHERE m.tenant_id = c.tenant_id AND m.agent = c.agent "
    "AND m.conversation_id = c.id AND m.seq > c.cut_upto) ORDER BY c.last_at, c.id LIMIT :limit"
)
_UNCUT = text(
    "SELECT m.seq, m.conversation_id, m.external_id, m.sender_id, m.sender_name, m.role, m.origin, m.at, "
    "m.text, m.answered FROM agent_rt.cv_message m JOIN agent_rt.cv_conversation c "
    "ON c.tenant_id = m.tenant_id AND c.agent = m.agent AND c.id = m.conversation_id "
    "WHERE m.tenant_id = :tenant_id AND m.agent = :agent AND m.conversation_id = ANY(:ids) "
    "AND m.seq > c.cut_upto ORDER BY m.conversation_id, m.seq LIMIT :limit"
).bindparams(bindparam("ids", type_=ARRAY(Text)))
_MARK_CUT = text(
    "UPDATE agent_rt.cv_conversation SET cut_upto = GREATEST(cut_upto, :seq) "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)


class PostgresConversationStore:
    def __init__(self, engine: AsyncEngine, *, tenant_id: str, agent: str) -> None:
        self._engine = engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def add(self, message: NewMessage) -> bool:
        params = {
            **self._scope,
            "id": message.conversation_id,
            "channel": message.channel,
            "external_id": message.external_id,
            "is_group": message.is_group,
            "title": message.title_hint,
            "at": message.at,
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "role": message.role,
            "origin": message.origin,
            "text": message.text,
            "answered": message.answered,
            "meta": json.dumps(message.meta, ensure_ascii=False),
        }
        async with self._engine.begin() as conn:
            excluded = (await conn.execute(_UPSERT_CONVERSATION, params)).scalar_one()
            if excluded:
                return False
            if (await conn.execute(_INSERT_MESSAGE, params)).first() is None:
                return False
            await conn.execute(_TOUCH, params)
        return True

    async def conversations(
        self, *, channel: str | None, query: str, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        params: dict[str, Any] = {
            **self._scope,
            "channel": channel,
            "like": _like(query.strip()) if query.strip() else None,
        }
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_LIST, {**params, "limit": limit, "offset": offset})).mappings().all()
            total = (await conn.execute(_COUNT, params)).scalar_one()
        return [_conversation(row) for row in rows], int(total)

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_GET, {**self._scope, "id": conversation_id})).mappings().one_or_none()
        return None if row is None else _conversation(row)

    async def messages(self, conversation_id: str, *, limit: int) -> list[Message]:
        async with self._engine.connect() as conn:
            rows = (
                (await conn.execute(_MESSAGES, {**self._scope, "id": conversation_id, "limit": limit}))
                .mappings()
                .all()
            )
        return [_message(row) for row in rows]

    async def set_excluded(self, conversation_id: str, excluded: bool) -> bool:
        async with self._engine.begin() as conn:
            done = await conn.execute(_EXCLUDE, {**self._scope, "id": conversation_id, "excluded": excluded})
        return done.rowcount > 0

    async def delete(self, conversation_id: str) -> bool:
        async with self._engine.begin() as conn:
            done = await conn.execute(_DELETE, {**self._scope, "id": conversation_id})
        return done.rowcount > 0

    async def delete_many(self, conversation_ids: Sequence[str]) -> int:
        async with self._engine.begin() as conn:
            done = await conn.execute(_DELETE_MANY, {**self._scope, "ids": list(conversation_ids)})
        return done.rowcount

    async def purge_before(self, cutoff: datetime) -> int:
        async with self._engine.begin() as conn:
            gone = (await conn.execute(_PURGE, {**self._scope, "cutoff": cutoff})).rowcount
            if gone:
                await conn.execute(_RECOUNT, self._scope)
                await conn.execute(_DROP_EMPTY, self._scope)
        return gone

    async def people(self, channel: str) -> list[Person]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_PEOPLE, {**self._scope, "channel": channel})).mappings().all()
        return [
            Person(r["sender_id"], r["name"] or "", int(r["messages"]), cast(Role, r["role"])) for r in rows
        ]

    async def to_cut(self, *, idle_before: datetime, limit: int) -> list[Conversation]:
        async with self._engine.connect() as conn:
            rows = (
                (await conn.execute(_TO_CUT, {**self._scope, "before": idle_before, "limit": limit}))
                .mappings()
                .all()
            )
        return [_conversation(row) for row in rows]

    async def uncut_messages(
        self, conversation_ids: Sequence[str], *, limit: int
    ) -> dict[str, list[Message]]:
        found: dict[str, list[Message]] = {cid: [] for cid in conversation_ids}
        if not conversation_ids:
            return found
        params = {**self._scope, "ids": list(conversation_ids), "limit": limit}
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_UNCUT, params)).mappings().all()
        for row in rows:
            found[row["conversation_id"]].append(_message(row))
        return found

    async def mark_cut(self, marks: Mapping[str, int]) -> None:
        if not marks:
            return
        rows = [{**self._scope, "id": cid, "seq": seq} for cid, seq in marks.items()]
        async with self._engine.begin() as conn:
            await conn.execute(_MARK_CUT, rows)

    async def relabel(self, channel: str, sender_ids: Collection[str], role: Role) -> int:
        if not sender_ids:
            return 0
        params = {**self._scope, "channel": channel, "sender_ids": list(sender_ids), "role": role}
        async with self._engine.begin() as conn:
            return (await conn.execute(_RELABEL, params)).rowcount


def _conversation(row: Any) -> Conversation:
    return Conversation(
        id=row["id"],
        channel=row["channel"],
        external_id=row["external_id"],
        is_group=row["is_group"],
        title=row["title"],
        excluded=row["excluded"],
        message_count=row["message_count"],
        first_at=row["first_at"],
        last_at=row["last_at"],
    )


def _message(row: Any) -> Message:
    return Message(
        seq=row["seq"],
        conversation_id=row["conversation_id"],
        message_id=row["external_id"],
        sender_id=row["sender_id"],
        sender_name=row["sender_name"],
        role=row["role"],
        origin=row["origin"],
        at=row["at"],
        text=row["text"],
        answered=row["answered"],
    )
