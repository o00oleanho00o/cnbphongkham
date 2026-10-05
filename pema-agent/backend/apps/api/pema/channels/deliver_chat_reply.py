# ported from: src/zalo/deliver-chat-reply.ts
"""Giao câu trả lời của agent xuống kênh cho lượt chat THƯỜNG: làm sạch -> (chính sách) -> gửi -> ghi history.

Tách khỏi ``message_turn_processor`` vì đó là phần ĐIỀU PHỐI cả lượt (mở lượt, lưu ảnh, chốt usage, lưu trace,
nhánh lỗi) - còn đây là một việc gọn: biến chữ của model thành tin trên kênh.

KHÔNG dùng chung với scheduler: lượt theo lịch có luật ``[SILENT]`` riêng phải chạy TRƯỚC bước làm sạch,
và job
hỏng thì im chứ không nhắn câu lỗi.

Channel-agnostic: both channels use it. The ONE addition over the original is the policy gate (PLAN-AI01
section 5):
between the sanitising shield and the send, ``PolicyHooks.on_outbound`` decides ``SEND``
(``staff_assistant``),
``HOLD_FOR_REVIEW`` (``patient_channel``: a ``review_item`` is created and NOTHING is sent) or ``DROP``.
A text
held for review is held in its SANITISED form (before the markdown translation, which is deterministic and is
applied again when a person approves and the text goes out through this same function with
``human_approved=True``). If the policy says hold and no hold function is configured, the text is NOT sent
(fail closed).

Forced deviations: async; ``appendMessage`` is ``HistoryStore.append_message(clinic_id, ...)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pema.channels.prepare_outgoing_text import dinh_dang_neu_bat, lam_sach_theo_cau_hinh
from pema.channels.send_reply_in_parts import (
    EnqueueSend,
    ReplyTarget,
    send_reply_in_parts,
)
from pema.channels.turn_ports import FailureNotifier, HoldForReview
from pema.shared.logger import create_logger
from pema_contracts.conversation import HistoryStore, StoredMessage
from pema_contracts.policy import (
    OutboundAction,
    OutboundOrigin,
    PolicyContext,
    PolicyHooks,
)

log = create_logger("message-turn")


@dataclass
class KetQuaGiao:
    da_gui: str
    """Chữ THẬT SỰ đã tới kênh - rỗng khi bị chặn, bị giữ để duyệt hoặc không gửi được gì."""
    hong: bool
    """Bị chặn vì rò system prompt, hoặc gửi hỏng giữa chừng."""
    held_for_review: bool = False
    """The policy held the text for a person; nothing was sent."""
    review_item_id: str | None = None
    dropped: bool = False


@dataclass
class DeliveryDeps:
    history: HistoryStore
    hooks: PolicyHooks
    policy: PolicyContext
    enqueue_send: EnqueueSend | None = None
    hold_for_review: HoldForReview | None = None
    notify_failure: FailureNotifier | None = None


async def deliver_chat_reply(
    target: ReplyTarget,
    deps: DeliveryDeps,
    clinic_id: UUID,
    account_id: str,
    thread_id: str,
    text: str,
    *,
    human_approved: bool = False,
) -> KetQuaGiao:
    """``human_approved=True`` is the path of a review item a person approved (the same send path: sanitise,
    translate, split, send, record). It skips the policy gate because the human decision IS the gate."""
    # Lớp làm sạch CUỐI trước khi chữ ra kênh. Hai đường khác nhau ở chỗ dấu markdown bị XÓA hay được
    # DỊCH thành
    # định dạng thật của Zalo; lá chắn rò system prompt và luật `[SILENT]` thì cả hai đều có.
    sach = lam_sach_theo_cau_hinh(text)

    if sach.chan:
        # Câu trả lời rò system prompt. Cắt bớt rồi gửi phần còn lại là gửi nửa vời - không ai biết phần
        # nào còn
        # rò. Chặn hẳn, báo lỗi kỹ thuật. Only the length is logged: NEVER the leaked prompt nor the answer.
        log.error("Chặn câu trả lời rò system prompt - không gửi", do_dai=len(text))
        if deps.notify_failure is not None:
            await deps.notify_failure(None)
        return KetQuaGiao(da_gui="", hong=True)

    if sach.da_sua:
        # Sửa chữ của model rồi im lặng là tự bịt mắt mình lúc chẩn đoán
        log.warning("Đã làm sạch câu trả lời trước khi gửi", da_sua=sach.da_sua)

    # Dịch markdown thành `TextStyle` của Zalo. Chữ TRẦN sau bước này mới là chữ người dùng thấy, nên nó
    # cũng là
    # chữ ghi vào history bên dưới.
    dinh_dang = dinh_dang_neu_bat(sach.text)
    chu_gui, styles = dinh_dang.text, dinh_dang.styles

    # Kiểm rỗng SAU khi dịch: câu chỉ toàn dấu markdown (vd đúng một hàng rào code trống) còn chữ trước
    # bước này
    # nhưng rỗng sau, gửi đi là gửi tin trắng.
    if not chu_gui.strip():
        log.debug("Câu trả lời rỗng sau khi làm sạch - không gửi")
        return KetQuaGiao(da_gui="", hong=False)

    if not human_approved:
        decision = await deps.hooks.on_outbound(
            deps.policy, sach.text, proactive=False, origin=OutboundOrigin.TURN_REPLY
        )
        if decision.action is OutboundAction.DROP:
            log.info("policy dropped the reply", account_id=account_id, reason=decision.reason)
            return KetQuaGiao(da_gui="", hong=False, dropped=True)
        if decision.action is OutboundAction.HOLD_FOR_REVIEW:
            item_id = None
            if deps.hold_for_review is not None:
                item_id = await deps.hold_for_review(sach.text, origin=OutboundOrigin.TURN_REPLY)
            if item_id is None:
                # Fail closed: the policy said a person must decide, so with no review item there is no send.
                log.error(
                    "reply held by policy but no review item could be created - not sent",
                    account_id=account_id,
                )
            return KetQuaGiao(da_gui="", hong=item_id is None, held_for_review=True, review_item_id=item_id)

    # Tin dài bị Zalo chặn (error_code 118) nên phải cắt thành nhiều đoạn
    reply = await send_reply_in_parts(target, chu_gui, styles, enqueue_send=deps.enqueue_send)

    # Chỉ ghi phần ĐÃ gửi được: history phải khớp cái người dùng nhìn thấy. Ghi chữ ĐÃ LÀM SẠCH chứ không phải
    # chữ gốc - lệch thì lượt sau model đọc lại history, thấy chính nó từng viết markdown và tưởng thế là
    # được.
    if reply.delivered_text:
        await deps.history.append_message(
            clinic_id, account_id, thread_id, StoredMessage(role="assistant", content=reply.delivered_text)
        )

    # Gửi dở giữa chừng cũng phải nói, đừng để người ta ngồi đợi nốt phần sau
    if reply.error is not None:
        if deps.notify_failure is not None:
            await deps.notify_failure(None)
        return KetQuaGiao(da_gui=reply.delivered_text, hong=True)

    return KetQuaGiao(da_gui=reply.delivered_text, hong=False)
