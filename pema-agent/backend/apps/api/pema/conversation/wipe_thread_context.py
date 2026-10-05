# ported from: src/conversation/wipe-thread-context.ts
"""Xóa sạch ngữ cảnh của MỘT cuộc trò chuyện: bot quên hẳn, như chưa từng nói chuyện với người này.

Forced deviations:

* the original explains that the SQLite schema had NO foreign keys, so nothing cascaded and every table had
  to be emptied by hand. The Postgres schema has some (``usage_steps`` -> ``usage``, ``threads`` ->
  ``accounts``) but NONE that links history, memories, contacts, image descriptions or proactive counters to
  a thread, so the explicit list below is still the only thing that makes the wipe complete: do not rely on
  cascade;
* ``proactive_send_counters`` is keyed by ``scope_key`` (``"<account>:<thread>"`` in ``staff_assistant``,
  per patient in ``patient_channel``, see ``PolicyHooks.proactive_cap``) instead of ``account_id`` +
  ``thread_id``. Only the per-thread key is deleted: a per-patient cap must NOT be reset by wiping one
  conversation (the daily cap protects the patient, not the thread);
* the files of the thread are on the local volume (``MediaStore``) and are deleted AFTER the transaction, as
  in the original.

VÌ SAO PHẢI GOM VÀO MỘT CHỖ: rải lệnh xóa ra nhiều nơi là kiểu bỏ sót không ai phát hiện: dữ liệu nằm lại âm
thầm, người dùng tưởng đã sạch, rồi bot nhắc lại chuyện cũ ở lượt sau. For a clinic the same omission is a
data retention failure (Decree 13/2023: the patient asked to be forgotten).

GIỮ LẠI có chủ đích, không phải quên:
  - Dòng ``threads``: giữ tên hiển thị và công tắc bật/tắt bot. Đây là "reset" theo nghĩa của goclaw (xóa
    lịch sử, GIỮ session), không phải "delete".
  - ``jobs`` (scheduled): lịch hẹn là LỜI ĐÃ HỨA với người dùng, khác hẳn ngữ cảnh. Xóa trí nhớ mà nuốt luôn
    lời hẹn là kết cục không ai lường trước.
  - ``contacts``: theo account, không theo thread.
  - ``usage``: SỔ CHI TIÊU token, không chứa chữ nào của hội thoại. Nội dung trace nằm ở ``usage_steps`` và
    bị xóa - xem ``_DELETE_STEPS``.
  - ``memories``: CHỈ xóa khi người dùng tick riêng - xem ``wipe_memories``.

Phần DB chạy trong MỘT giao dịch: xóa nửa chừng rồi hỏng còn tệ hơn không xóa, vì lúc đó không ai biết bot
còn nhớ những gì. Riêng file trên đĩa nằm ngoài giao dịch (không thể rollback được) nên xóa SAU khi DB đã
cam kết - mất file mà DB còn dòng thì chỉ là ảnh hỏng; ngược lại là dòng trỏ vào hư vô.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from pema.conversation.image_description_store import ImageDescriptionStoreImpl
from pema.conversation.media_store import MediaStore
from pema.conversation.sql_util import affected_rows
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger

_log = create_logger("wipe-thread")


@dataclass(frozen=True)
class WipeOptions:
    """``TuyChonXoa``."""

    wipe_memories: bool = False
    """Xóa luôn fact bền đã học TRONG thread này (``memories.learned_in_thread_id``) - ``xoaTriNho``.

    Mặc định KHÔNG xóa: trí nhớ gắn với CON NGƯỜI (``subject_id``) chứ không gắn với cuộc trò chuyện, nên xóa
    lịch sử một thread mà bốc hơi luôn "anh Hải ở TP.HCM" là mất thứ người dùng không hề định bỏ. Lọc theo
    ``learned_in_thread_id`` nên fact học ở thread khác về cùng người vẫn còn.
    """


@dataclass(frozen=True)
class WipeResult:
    """``KetQuaXoaNguCanh``."""

    messages: int
    """``tinNhan``."""
    agent_steps: int
    """``buocAgent``: số step trace đã xóa. Dòng đếm token (``usage``) GIỮ NGUYÊN - xem ``_DELETE_STEPS``."""
    images: int
    """``anh``."""
    image_descriptions: int
    """``moTaAnh``."""
    memories: int
    """``triNho``."""
    proactive_counters: int
    """``soDemChuDong``."""
    new_epoch: int
    """``epochMoi``: epoch mới sau khi tăng - khóa phiên gửi router đổi theo số này."""


_DELETE_MESSAGES = text(
    "DELETE FROM agent.history "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

# Xóa NỘI DUNG trace (``usage_steps``), GIỮ dòng đếm (``usage``).  Hai bảng này khác hẳn bản chất:
# ``usage_steps`` chứa nguyên văn tin nhắn, suy luận, tham số và kết quả tool - đúng thứ phải quên. Còn
# ``usage`` chỉ có ``input_tokens/output_tokens/created_at/source``, KHÔNG một chữ nào của hội thoại - nó là
# SỔ CHI TIÊU, và nó là nguồn duy nhất của thống kê token (``usage_store``).  Bản đầu xóa cả hai, và đo trên
# máy người dùng sau 4 lần xóa thử: trang Tổng quan báo hôm nay dùng 0 token trong khi bot chạy ~30 lượt.
# Xóa một cuộc trò chuyện thì phải quên nội dung, nhưng không có lý do gì để viết lại số tiền đã tiêu.  Đổi
# lại tab Trace của thread đã xóa liệt kê lượt cũ mà mở ra không có step - giao diện đã có sẵn dòng "Lượt
# này không có step nào được ghi". Như vậy còn trung thực hơn: lượt đó có chạy thật và có tốn ngần ấy token.
_DELETE_STEPS = text(
    """
    DELETE FROM agent.usage_steps
    WHERE clinic_id = :clinic_id
      AND turn_id IN (SELECT id FROM agent.usage
                      WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id)
    """
)

_DELETE_COUNTERS = text(
    "DELETE FROM agent.proactive_send_counters WHERE clinic_id = :clinic_id AND scope_key = :scope_key"
)

_DELETE_MEMORIES = text(
    "DELETE FROM agent.memories "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND learned_in_thread_id = :thread_id"
)

# Dọn summary và tăng epoch trong CÙNG một câu lệnh.  Gộp chung chứ không tách hai lệnh: quên tăng epoch thì
# router vẫn giữ tiền tố đã cache của cuộc trò chuyện vừa xóa, mà đó là kiểu sót không lộ ra ở bất kỳ phép
# kiểm nào trong DB. Cũng đặt lại ``message_count`` vì lịch sử đã trống - để nguyên thì trang Sessions hiện
# "465 tin" cho một thread không còn tin nào. ``RETURNING`` đọc luôn epoch mới (the original did a second
# SELECT).
_RESET_THREAD = text(
    """
    UPDATE agent.threads
       SET summary = '', summary_covers_to_message_id = 0,
           message_count = 0, context_epoch = context_epoch + 1
     WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
    RETURNING context_epoch
    """
)


class ThreadContextWiper:
    def __init__(
        self, db: ClinicDatabase, media: MediaStore, image_descriptions: ImageDescriptionStoreImpl
    ) -> None:
        self._db = db
        self._media = media
        self._image_descriptions = image_descriptions

    async def wipe_thread_context(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        options: WipeOptions | None = None,
    ) -> WipeResult:
        """``xoaNguCanhThread``."""
        opts = options or WipeOptions()
        scope = {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}

        async with self._db.session() as session:
            agent_steps = affected_rows(await session.execute(_DELETE_STEPS, scope))
            messages = affected_rows(await session.execute(_DELETE_MESSAGES, scope))
            counters = affected_rows(
                await session.execute(
                    _DELETE_COUNTERS, {"clinic_id": clinic_id, "scope_key": f"{account_id}:{thread_id}"}
                )
            )
            memories = (
                affected_rows(await session.execute(_DELETE_MEMORIES, scope)) if opts.wipe_memories else 0
            )
            epoch = (await session.execute(_RESET_THREAD, scope)).scalar()

        # Ngoài giao dịch, và CỐ Ý chạy sau: file mất mà DB còn dòng chỉ là ảnh hỏng, còn DB xóa rồi mà file
        # còn thì dọn rác định kỳ sẽ lo (media có TTL sẵn).
        image_paths = await self._media.delete_thread_media(clinic_id, account_id, thread_id)
        described = await self._image_descriptions.delete_descriptions_by_paths(clinic_id, image_paths)

        result = WipeResult(
            messages=messages,
            agent_steps=agent_steps,
            images=len(image_paths),
            image_descriptions=described,
            memories=memories,
            proactive_counters=counters,
            new_epoch=int(epoch) if epoch is not None else 0,
        )
        _log.info(
            "Đã xóa ngữ cảnh thread",
            account_id=account_id,
            thread_id=thread_id,
            messages=result.messages,
            agent_steps=result.agent_steps,
            images=result.images,
            image_descriptions=result.image_descriptions,
            memories=result.memories,
            proactive_counters=result.proactive_counters,
            new_epoch=result.new_epoch,
            wipe_memories=opts.wipe_memories,
        )
        return result
