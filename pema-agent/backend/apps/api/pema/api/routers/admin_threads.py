# ported from: src/server/routes/thread-routes.ts
"""Threads, messages, contacts and memories (package D2 implements).

Port of thread-routes.ts, contact-routes.ts and memory-routes.ts. ``history`` content is staff-only and
lives in ``agent.history``; it is not the Inbox of record (``/conversations`` is).

Forced deviations: Hono + zod become FastAPI; the responses follow the OpenAPI skeleton (a ``ThreadRow``
list, 204 instead of ``{ok: true, ...counts}``); ``page``/``pageSize`` + ``hasMore`` became
``limit``/``offset``.

Kept from the original, with the reasons of its comments:

* ``DELETE .../history`` wipes the whole context of a conversation: messages, summary, trace, downloaded
  images; ``xoaTriNho=true`` also deletes the durable facts learned IN this thread. The option is read from
  the raw query string and ONLY the exact string ``true`` turns it on: accepting any "truthy" value would
  let a mistyped URL (``?xoaTriNho=0``) delete memory. It is not declared in the OpenAPI skeleton (a
  contract change goes through package G, see the report); the route works without it;
* the pending batch is cancelled BEFORE the database is touched (``AdminStores.cancel_pending_batch``);
* there is NO command for it in the chat (goclaw has ``/reset`` for the writer of a group). The bot reads
  messages of strangers, so a wipe through chat is an attack surface not worth the trade; the dashboard has
  a session and a permission;
* ``DELETE .../summary`` sets ``summary_covers_to_message_id`` back to 0, not only the text: that column is
  the mark of "folded up to which message". Keeping it would make the next summary fold only the NEW backlog
  and the old part of the conversation would be lost instead of rewritten. At 0 the next fold re-reads from
  the start and builds a new one, costing exactly one LLM call (the summary path only runs when the backlog
  is big, after the reply, so nobody waits for it);
* ``DELETE /threads/{account}/{thread}`` removes the session row too (and its scheduled jobs), keeping
  contacts (Phương án A) and memory (it has its own button); ``DELETE .../history`` only resets (keeps the
  row).

Every mutation is audited when an audit sink is wired (ids and counts only, never text).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Query, Request, status

from pema.api.deps import Limit, Offset, admin_router
from pema.api.routers.admin_stores import AdminStores, ClinicId, Stores, record_audit
from pema.conversation.wipe_thread_context import WipeOptions
from pema_contracts.admin_agent import ThreadUpdate
from pema_contracts.conversation import ContactRow, MemoryFact, StoredMessage, ThreadRow
from pema_contracts.errors import DomainError, ErrorCode

router = admin_router("threads", "admin-threads")
contacts_router = admin_router("contacts", "admin-threads")
memories_router = admin_router("memories", "admin-threads")


def _thread_not_found() -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, "Thread không tồn tại.")


@router.get("", response_model=list[ThreadRow], summary="Threads of one or all accounts")
async def list_threads(
    clinic_id: ClinicId,
    stores: Stores,
    account_id: str | None = None,
    q: str = Query(default="", max_length=120),
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[ThreadRow]:
    # accountId bỏ trống = xem trộn mọi account (lọc bằng dropdown trong trang)
    return await stores.conversation.list_threads(
        clinic_id, account_id=account_id, query=q, limit=limit, offset=offset
    )


@router.get(
    "/{account_id}/{thread_id}/messages",
    response_model=list[StoredMessage],
    summary="History of a thread, keyset-paged by id",
)
async def list_thread_messages(
    account_id: str,
    thread_id: str,
    clinic_id: ClinicId,
    stores: Stores,
    before_id: int | None = None,
    limit: Limit = 50,
) -> list[StoredMessage]:
    return await stores.conversation.list_messages_paged(
        clinic_id, account_id, thread_id, limit=limit, before_id=before_id
    )


@router.patch(
    "/{account_id}/{thread_id}", response_model=ThreadRow, summary="Rename or switch the bot on/off"
)
async def update_thread(
    account_id: str, thread_id: str, clinic_id: ClinicId, stores: Stores, body: ThreadUpdate
) -> ThreadRow:
    conversation = stores.conversation
    if await conversation.get_thread(clinic_id, account_id, thread_id) is None:
        raise _thread_not_found()
    if body.bot_enabled is not None:
        await conversation.set_bot_enabled(clinic_id, account_id, thread_id, body.bot_enabled)
    if body.display_name is not None:
        await conversation.set_thread_display_name(clinic_id, account_id, thread_id, body.display_name)

    updated = await conversation.get_thread(clinic_id, account_id, thread_id)
    if updated is None:  # deleted in between
        raise _thread_not_found()
    await record_audit(
        stores,
        clinic_id,
        "thread.update",
        "thread",
        f"{account_id}:{thread_id}",
        {"bot_enabled": body.bot_enabled, "renamed": body.display_name is not None},
    )
    return updated


@router.delete(
    "/{account_id}/{thread_id}/summary",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the rolling summary",
)
async def clear_thread_summary(account_id: str, thread_id: str, clinic_id: ClinicId, stores: Stores) -> None:
    await stores.conversation.set_thread_summary(clinic_id, account_id, thread_id, "", 0)
    await record_audit(stores, clinic_id, "thread.clear_summary", "thread", f"{account_id}:{thread_id}", {})


@router.delete(
    "/{account_id}/{thread_id}/history",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Wipe history, summary and media (bumps the context epoch)",
)
async def wipe_thread_history(
    request: Request, account_id: str, thread_id: str, clinic_id: ClinicId, stores: Stores
) -> None:
    # Only the exact string "true" turns the memory wipe on (see module docstring).
    wipe_memories = request.query_params.get("xoaTriNho") == "true"

    pending = await _cancel_pending(stores, clinic_id, account_id, thread_id)
    result = await stores.conversation.wiper.wipe_thread_context(
        clinic_id, account_id, thread_id, WipeOptions(wipe_memories=wipe_memories)
    )
    await record_audit(
        stores,
        clinic_id,
        "thread.wipe_history",
        "thread",
        f"{account_id}:{thread_id}",
        {
            "messages": result.messages,
            "images": result.images,
            "memories": result.memories,
            "wipe_memories": wipe_memories,
            "pending_cancelled": pending,
        },
    )


@router.delete(
    "/{account_id}/{thread_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete the thread entirely"
)
async def delete_thread(account_id: str, thread_id: str, clinic_id: ClinicId, stores: Stores) -> None:
    # Hủy hàng chờ TRƯỚC khi xóa: một batch đang đỗ mà chạy xen vào sẽ dựng lại session vừa xóa.
    pending = await _cancel_pending(stores, clinic_id, account_id, thread_id)
    result = await stores.conversation.delete_thread(clinic_id, account_id, thread_id)
    await record_audit(
        stores,
        clinic_id,
        "thread.delete",
        "thread",
        f"{account_id}:{thread_id}",
        {
            "messages": result.messages,
            "jobs": result.jobs,
            "had_row": result.had_row,
            "pending_cancelled": pending,
        },
    )


async def _cancel_pending(stores: AdminStores, clinic_id: UUID, account_id: str, thread_id: str) -> int:
    """Hủy hàng chờ TRƯỚC khi xóa DB (``huyBatchCuaThread``); 0 when no batcher is wired."""
    if stores.cancel_pending_batch is None:
        return 0
    return await stores.cancel_pending_batch(clinic_id, account_id, thread_id)


@contacts_router.get("", response_model=list[ContactRow], summary="Contacts")
async def list_contacts(
    clinic_id: ClinicId,
    stores: Stores,
    account_id: str | None = None,
    q: str = Query(default="", max_length=120),
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[ContactRow]:
    return await stores.conversation.list_contacts(
        clinic_id, account_id=account_id, query=q, limit=limit, offset=offset
    )


@contacts_router.delete(
    "/{account_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a contact"
)
async def delete_contact(account_id: str, user_id: str, clinic_id: ClinicId, stores: Stores) -> None:
    # Xóa MỘT dòng danh bạ (không đụng tin nhắn). ``account_id`` nằm trong đường dẫn vì khóa là (account_id,
    # user_id) - thiếu nó sẽ xóa nhầm cùng user_id ở account khác. Deleting a contact that is not there is
    # not an error (the original answered ``{ok: false}``).
    deleted = await stores.conversation.delete_contact(clinic_id, account_id, user_id)
    if deleted:
        await record_audit(stores, clinic_id, "contact.delete", "contact", f"{account_id}:{user_id}", {})


@memories_router.get("", response_model=list[MemoryFact], summary="Durable memory facts")
async def list_memories(
    clinic_id: ClinicId,
    stores: Stores,
    account_id: str | None = None,
    q: str = Query(default="", max_length=120),
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[MemoryFact]:
    return await stores.conversation.list_memories(
        clinic_id, account_id=account_id, query=q, limit=limit, offset=offset
    )


@memories_router.delete(
    "/{account_id}/{fact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a memory fact"
)
async def delete_memory(account_id: str, fact_id: int, clinic_id: ClinicId, stores: Stores) -> None:
    if not await stores.conversation.delete_memory_fact(clinic_id, account_id, fact_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Fact không tồn tại.")
    await record_audit(stores, clinic_id, "memory.delete", "memory", f"{account_id}:{fact_id}", {})
