"""``PostgresConversationStore``: every Protocol of ``pema_contracts.conversation`` as ONE object to inject.

No zalo-agent source file: the original exposed the stores as module-level functions over a global SQLite
handle. Here each store is a class over a ``ClinicDatabase`` (see the modules it comes from) and this class
is the composition the consumers receive (D1 engine, channel turn processor, scheduler, admin routes) typed
as ``ConversationStore``.

``wipe_thread_context`` of the contract returns ``None`` and wipes without the memory option; the admin route
needs the options and the counts, so it uses ``ThreadContextWiper`` directly (``self.wiper``).
"""

from __future__ import annotations

from uuid import UUID

from pema.conversation.agent_trace_store import AgentTraceStore
from pema.conversation.contact_store import ContactStoreImpl
from pema.conversation.history_store import HistoryStoreImpl
from pema.conversation.image_description_store import ImageDescriptionStoreImpl
from pema.conversation.media_store import MediaStore
from pema.conversation.memory_edit_store import MemoryEditStoreImpl
from pema.conversation.memory_store import MemoryStoreImpl
from pema.conversation.thread_store import ThreadStoreImpl
from pema.conversation.thread_summarizer import ThreadSummarizer
from pema.conversation.usage_store import UsageStoreImpl
from pema.conversation.wipe_thread_context import ThreadContextWiper
from pema.conversation.xoa_han_session import DeleteSessionResult, delete_thread_session
from pema.core.db import ClinicDatabase
from pema_contracts.agent_turn import TextGenerator


class PostgresConversationStore(
    HistoryStoreImpl,
    MemoryStoreImpl,
    ThreadStoreImpl,
    UsageStoreImpl,
    ContactStoreImpl,
    ImageDescriptionStoreImpl,
):
    def __init__(
        self,
        db: ClinicDatabase,
        media: MediaStore | None = None,
        text_generator: TextGenerator | None = None,
    ) -> None:
        HistoryStoreImpl.__init__(self, db)
        MemoryStoreImpl.__init__(self, db)
        ThreadStoreImpl.__init__(self, db)
        self.traces = AgentTraceStore(db)
        UsageStoreImpl.__init__(self, db, self.traces)
        ContactStoreImpl.__init__(self, db)
        ImageDescriptionStoreImpl.__init__(self, db)
        self.media = media or MediaStore()
        self.memory_edits = MemoryEditStoreImpl(db)
        self.wiper = ThreadContextWiper(db, self.media, self)
        self.summarizer = ThreadSummarizer(db, self, text_generator)

    async def wipe_thread_context(self, clinic_id: UUID, account_id: str, thread_id: str) -> None:
        """``wipe-thread-context.ts``: history, summary, trace and media; bumps ``context_epoch``."""
        await self.wiper.wipe_thread_context(clinic_id, account_id, thread_id)

    async def delete_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> DeleteSessionResult:
        """``xoaHanSession``: the wipe plus the thread row and its scheduled jobs."""
        return await delete_thread_session(self._db, self.wiper, clinic_id, account_id, thread_id)
