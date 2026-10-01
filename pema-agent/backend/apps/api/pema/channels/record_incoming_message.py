# ported from: src/zalo/record-incoming-message.ts
"""Write an incoming message to the history AT RECEIPT, and stamp the row id on the message itself.

Before, a message that got a reply was written at the END of the turn, while a passive-listen message was
written at once: two paths, two moments. All of it moved to "write at receipt" for three reasons, in order of
importance:

1. ORDER. Writing at the end of a turn means the order in the database is the order turns FINISHED, not the
  order people sent. While turns run serially the two coincide; once turns can run in parallel (a later phase)
  a fast turn jumps ahead of a slow one and the history tells the story in the wrong order.
2. LOST MESSAGES. A turn that dies because the process was killed mid-way makes the message vanish from
  history, although the sender already got the "received" signal.
3. One special branch less: the place for "message dropped because the queue hit its cap" had to write by
  itself because ``processBatch`` was the ONLY writer for the answered branch. Now every message takes the
  same path.

The price: the agent turn that reads history finds ITS OWN messages already in it. ``build_turn_messages``
filters by ``history_row_id`` so the model does not see them twice; that is why this function must stamp the
id on the message.

Forced deviations (SQLite -> Postgres, two stores, CONTRACTS section 4):

* The history store is ``HistoryStore`` (``agent.history``) and ``async``. ``ParsedMessage`` is
  ``InboundMessage``.
* NEW: the Inbox of record (``clinic.conversation`` / ``clinic.message``, what staff read) is written first,
  through ``AgentFacingClinicActions.record_inbound_message`` (idempotent on ``update_id``). A failure there
  raises ``InboxRecordError`` BEFORE anything is written to history, so a webhook retry is safe; a
  ``duplicate`` answer (the update was already recorded) writes nothing more. History failures are NOT caught
  here: the caller decides (the router logs and still answers, as the original did).
* ``persist_images`` replaces ``persistBatchImages`` (package D2's media store) as an injected seam.
* ``describe_for_history`` mirrors ``describeForHistory`` of ``zalo-message-parser.ts`` (package C2); it is
  kept private here so this package does not import code that is not merged yet.

Shared by both channels (C2 imports it).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.channel import InboundMessage
from pema_contracts.clinic_actions import InboxRef
from pema_contracts.conversation import StoredMessage
from pema_contracts.roles import ActorType

_log = create_logger("record-incoming-message")


class InboxWriter(Protocol):
    """The one ``AgentFacingClinicActions`` method this module uses."""

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef: ...


class HistoryWriter(Protocol):
    """The two ``HistoryStore`` methods this module uses (``ConversationStore`` satisfies it)."""

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int: ...

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: list[str]) -> None: ...


ImagePersister = Callable[[UUID, str, Sequence[InboundMessage]], Awaitable[None]]
"""``persist_batch_images(clinic_id, account_id, messages)``: download the images and set ``local_path``."""

_background: set[asyncio.Task[None]] = set()


class InboxRecordError(Exception):
    """The Inbox of record could not be written. Nothing was written to history."""


@dataclass(frozen=True)
class RecordedMessage:
    history_row_id: int | None
    """``None`` when the update was already recorded (``duplicate``)."""
    inbox: InboxRef | None = None
    duplicate: bool = False


def webhook_action_context(clinic_id: UUID, request_id: str | None = None) -> ActionContext:
    """Actor of a channel intake: the system, acting for a webhook/poller (no staff user, no agent turn)."""
    return ActionContext(
        clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.WEBHOOK, request_id=request_id
    )


def describe_for_history(msg: InboundMessage) -> str:
    """Content written to history for one incoming message. An image cannot enter the text column, so a
    countable trace is left; a message with only an image still needs text, otherwise the next turn reads an
    empty row and cannot tell what happened."""
    image_note = f" [gửi kèm {len(msg.images)} ảnh]" if msg.images else ""
    return f"{msg.text}{image_note}".strip() or "[ảnh]"


def image_paths_of(images: Sequence[object]) -> list[str]:
    paths: list[str] = []
    for image in images:
        local_path = getattr(image, "local_path", None)
        if isinstance(local_path, str) and local_path:
            paths.append(local_path)
    return paths


async def ghi_tin_den_vao_history(
    *,
    clinic_id: UUID,
    account_id: str,
    msg: InboundMessage,
    luu_anh_ngay: bool,
    history: HistoryWriter,
    inbox: InboxWriter | None = None,
    ctx: ActionContext | None = None,
    persist_images: ImagePersister | None = None,
) -> RecordedMessage:
    """``ghiTinDenVaoHistory``. ``luu_anh_ngay``: download and attach the images right here.

    ``False`` when an agent turn is about to run: that turn persists the images itself (and AWAITS, because
    ``local_path`` must exist before it builds the content for the model) and attaches the paths to this row.
    Doing both downloads every image TWICE; ``persist_images`` overwrites the same path so the data is safe,
    but that is one wasted network fetch per image.

    Also stamps ``msg.history_row_id``: DELIBERATELY mutating the message. Everyone who holds it later
    (batcher, agent turn, mid-turn injection) needs to know which row is its own, and passing it by hand
    through four layers means one of them forgets sooner or later."""
    inbox_ref: InboxRef | None = None
    if inbox is not None:
        try:
            inbox_ref = await inbox.record_inbound_message(ctx or webhook_action_context(clinic_id), msg)
        except Exception as exc:
            raise InboxRecordError("không ghi được tin vào Inbox") from exc
        if inbox_ref.duplicate:
            return RecordedMessage(history_row_id=None, inbox=inbox_ref, duplicate=True)

    row_id = await history.append_message(
        clinic_id,
        account_id,
        msg.thread_id,
        StoredMessage(
            role="user",
            content=describe_for_history(msg),
            sender_name=msg.sender_name,
            sender_id=msg.sender_id,
            # NOT passing ``images``: at receipt they are not downloaded, ``local_path`` does not exist yet,
            # so the value would always be empty. The paths are attached later by ``gan_anh_vao_history``. The
            # moment the PERSON pressed send, not the moment this line ran.
            created_at=msg.sent_at,
        ),
    )
    msg.history_row_id = row_id

    if luu_anh_ngay and msg.images and persist_images is not None:
        task = asyncio.ensure_future(
            _persist_and_attach(clinic_id, account_id, msg, row_id, history, persist_images)
        )
        _background.add(task)
        task.add_done_callback(_background.discard)
    return RecordedMessage(history_row_id=row_id, inbox=inbox_ref)


async def _persist_and_attach(
    clinic_id: UUID,
    account_id: str,
    msg: InboundMessage,
    row_id: int,
    history: HistoryWriter,
    persist_images: ImagePersister,
) -> None:
    # ``persist_images`` does not reject, but ``set_message_images`` touches the DB, so it still needs a
    # guard: otherwise it becomes an unhandled task exception.
    try:
        await persist_images(clinic_id, account_id, [msg])
        await history.set_message_images(clinic_id, row_id, image_paths_of(msg.images))
    except Exception as exc:
        _log.debug("Không gắn được ảnh vào history", err=exc, history_row_id=row_id)


async def gan_anh_vao_history(
    clinic_id: UUID, history: HistoryWriter, messages: Sequence[InboundMessage]
) -> None:
    """Attach image paths to the rows already written, after the agent turn downloaded them.

    Skips a message with no ``history_row_id`` instead of raising: this is a BONUS step (images for later
    turns to look at again), not worth killing a turn that is going fine."""
    for msg in messages:
        paths = image_paths_of(msg.images)
        if msg.history_row_id is not None and paths:
            await history.set_message_images(clinic_id, msg.history_row_id, paths)
