# ported from: src/zalo/send-reply-in-parts.ts
"""Gửi câu trả lời của agent xuống kênh, cắt thành nhiều tin khi quá dài.

Zalo chặn tin dài ở phía server (error_code 118 "Nội dung quá dài") và zca-js ném thẳng lỗi lên - trước đây cả
câu trả lời biến mất không dấu vết. Giờ cắt theo ranh giới tự nhiên rồi gửi tuần tự qua rate-limiter (mỗi
tin có
delay ngẫu nhiên sẵn nên chuỗi tin trông như người gõ nhiều dòng, không phải bot xả).

This module is channel-agnostic and shared by BOTH channels and by the scheduler (``scheduled_job_send``
builds a
``ReplyTarget`` and calls ``send_reply_in_parts``). Before every part leaves, the policy layer has already
decided (``PolicyHooks.on_outbound`` is called by the CALLERS: ``deliver_chat_reply`` for a turn reply, the
scheduler for proactive messages), so what reaches this module may be sent.

Forced deviations:

* sync -> async; the per-thread send queue is injected (``enqueue_send``). Production uses
  ``pema.middleware.rate_limiter.enqueue_send`` (package C1, same ``(thread_key, task)`` signature), loaded
  lazily so this package does not depend on C1 at import time; tests inject an immediate queue;
* zca-js ``Style``/``ThreadType``/``SendMessageQuote`` become ``TextStyle``/``ThreadKind``/``QuoteRef`` of
  ``pema_contracts.channel``;
* a ``ChannelPort`` signals a guard (kill switch, cap, window, not a friend) by a REJECTED
``SendResult``, not an
  exception. ``reply_target_from_channel`` turns that into ``ChannelSendRejectedError``, which has no numeric
  ``code`` and therefore is never retried (``la_loi_may_chu_tu_choi`` stays exactly the original test);
* ``getTuning`` reads the tuning provider of package A.
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from pema.channels.reply_quote import trich_dan_trong_ngan_sach
from pema.channels.split_styled_message import (
    NganSachByteOptions,
    TinCoDinhDang,
    chia_theo_ngan_sach_byte,
    dem_doan_bo_dinh_dang,
)
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.channel import ChannelPort, QuoteRef, SendStatus, TextStyle, ThreadKind
from pema_contracts.errors import ErrorCode

log = create_logger("send-reply")

# Câu trả lời khi bot hỏng giữa chừng. Im lặng bỏ treo người nhắn là hành vi tệ nhất: họ không biết nên
# chờ hay
# nhắn lại.
TECHNICAL_ERROR_REPLY = (
    "Mình đang gặp trục trặc kỹ thuật nên chưa trả lời được tin này, bạn nhắn lại giúp mình sau ít phút nhé."
)

# Câu riêng cho từng loại lỗi provider.
#
# Một câu cho mọi thứ là nói dối người nhắn: "bot hết quota" và "mạng chập" đọc ra y hệt nhau, nên họ
# không biết
# nên chờ hay báo cho chủ bot.
#
# Cả ba câu đều viết bằng lời thường, KHÔNG lộ chi tiết kỹ thuật (mã lỗi, tên provider, endpoint) - người
# nhắn có
# thể là người lạ, chi tiết chỉ đi vào log.
LOI_THEO_LOAI: dict[str, str] = {
    "rate_limit": (
        "Mình đang bị quá tải nên chưa trả lời kịp tin này, bạn nhắn lại giúp mình sau vài phút nhé."
    ),
    # Đây là lỗi CẤU HÌNH, chờ bao lâu cũng không tự hết - phải nói khác hẳn câu "thử lại sau", kẻo người nhắn
    # ngồi đợi vô vọng.
    "auth": (
        "Phần kết nối của mình đang có vấn đề về cấu hình, mình đã báo lại cho chủ bot. Bạn nhắn lại sau nhé."
    ),
    # Khác `auth` ở chỗ chưa nhập gì cả, chứ không phải nhập sai. Người nhắn không cần biết chi tiết đó, nhưng
    # câu phải nói rõ là CHƯA DÙNG ĐƯỢC chứ không phải trục trặc thoáng qua - nếu không họ sẽ nhắn lại mỗi vài
    # phút.
    "cau_hinh": (
        "Bot mình chưa được cài đặt xong nên chưa trả lời được. "
        "Mình đã báo cho chủ bot, bạn quay lại sau nhé."
    ),
}


def cau_loi_theo_loai(loai: str | None) -> str:
    """Câu hợp với loại lỗi; loại lạ thì rơi về câu chung."""
    return (loai and LOI_THEO_LOAI.get(loai)) or TECHNICAL_ERROR_REPLY


@dataclass(frozen=True)
class DoanCanGui:
    """Một đoạn đã cắt sẵn, chuẩn bị gửi xuống kênh."""

    text: str
    styles: Sequence[TextStyle] = ()
    quote: QuoteRef | None = None


@dataclass(kw_only=True)
class ReplyTarget:
    gui_mot_doan: Callable[[DoanCanGui], Awaitable[object]]
    """Gửi MỘT đoạn. Mỗi kênh tự cung cấp cách gửi của mình - đây là ranh giới DUY NHẤT giữa logic
    cắt/chữa lỗi ở
    file này và API thật của kênh. Dựng bằng ``reply_target_from_channel`` cho một ``ChannelPort``."""
    thread_key: str
    """Khóa hàng đợi gửi của rate-limiter: ``f"{account_id}:{thread_id}"``."""
    thread_id: str
    thread_type: ThreadKind
    tran_ky_tu_mot_tin: int | None = None
    """Trần độ dài MỘT tin của kênh này; thiếu thì dùng ``ZALO_MAX_MESSAGE_CHARS``. Cần trường riêng vì
    hai kênh
    là hai giao thức khác nhau: Bot API ép cứng 2000 ký tự phía server (đo thật: gửi 2001 bị từ chối), còn
    ``ZALO_MAX_MESSAGE_CHARS`` chỉnh được tới 4000 trên dashboard."""
    mang_dinh_dang: bool | None = None
    """Kênh này có mang được định dạng không; thiếu = CÓ."""
    quote: QuoteRef | None = None
    """Tin được trích dẫn khi trả lời (chỉ nhóm - xem ``reply_quote``). Chỉ ĐOẠN ĐẦU của câu trả lời mang
    nó: các
    đoạn sau là phần nối tiếp của cùng một câu, trích lại ở mỗi đoạn chỉ tổ rối. Đường gửi của scheduler không
    đặt trường này - job theo lịch không trả lời tin nào cả."""


@dataclass
class ReplyResult:
    delivered_text: str
    """Phần đã gửi được thật sự - ghi vào history đúng cái người dùng nhìn thấy."""
    sent_parts: int
    """Số tin đã gửi."""
    error: BaseException | None = field(default=None)
    """Lỗi ở tin đầu tiên gửi hỏng (nếu có) - caller quyết định báo cho người dùng."""


type EnqueueSend = Callable[[str, Callable[[], Awaitable[object]]], Awaitable[object]]
"""``enqueueSend(threadKey, task)`` of ``middleware/rate-limiter.ts``: sequential per thread, random
delay before
each task."""


class ChannelSendRejectedError(Exception):
    """A ``ChannelPort`` answered a rejected ``SendResult`` (guard). Has NO numeric ``code`` on purpose:
    a guard
    is not a Zalo server refusal, so ``la_loi_may_chu_tu_choi`` is false and nothing is retried."""

    def __init__(self, error_code: ErrorCode | None, detail: str | None) -> None:
        super().__init__(f"channel rejected the send: {error_code.value if error_code else 'unknown'}")
        self.error_code = error_code
        self.detail = detail


def default_enqueue_send() -> EnqueueSend:
    """Production queue: ``pema.middleware.rate_limiter.enqueue_send`` (package C1). Loaded lazily."""
    module: Any = importlib.import_module("pema.middleware.rate_limiter")
    enqueue: EnqueueSend = module.enqueue_send
    return enqueue


def reply_target_from_channel(
    channel: ChannelPort,
    thread_id: str,
    thread_type: ThreadKind,
    thread_key: str,
    *,
    proactive: bool = False,
    quote: QuoteRef | None = None,
) -> ReplyTarget:
    """``duongGuiZcaJs`` + ``replyTargetTuKenh`` in one place: the ONE function that knows which fields of the
    channel travel down to the send path. They are all optional, so forgetting one is silent: missing
    ``tran_ky_tu_mot_tin`` makes the Bot channel lose a whole answer (the server refuses the whole message),
    missing ``mang_dinh_dang`` charges the byte budget for ``styles`` that are about to be dropped.

    ``proactive=True`` is for the scheduler: the channel then applies its proactive guard (kill switch,
    window,
    cap). Styles are attached only when non-empty and the quote only when present (zca-js builds
    ``textProperties`` only for a non-empty ``styles`` and switches to the ``.../quote`` endpoint when a
    quote is
    given, so an empty value would change the API call for nothing).
    """
    capabilities = channel.capabilities()

    async def gui_mot_doan(doan: DoanCanGui) -> object:
        result = await channel.send_text(
            thread_id,
            doan.text,
            thread_kind=thread_type,
            styles=doan.styles if doan.styles else (),
            quote=doan.quote,
            proactive=proactive,
        )
        if result.status is SendStatus.REJECTED:
            raise ChannelSendRejectedError(result.error_code, result.detail)
        return result

    return ReplyTarget(
        gui_mot_doan=gui_mot_doan,
        tran_ky_tu_mot_tin=capabilities.max_text_length,
        mang_dinh_dang=capabilities.supports_formatting,
        thread_key=thread_key,
        thread_id=thread_id,
        thread_type=thread_type,
        quote=quote,
    )


def la_loi_may_chu_tu_choi(err: BaseException | None) -> bool:
    """Máy chủ Zalo có TRẢ LỜI và từ chối, hay là lỗi đường truyền không rõ kết cục?

    Phân biệt được điều này mới dám gửi lại: máy chủ đã từ chối nghĩa là KHÔNG có tin nào lọt qua, gửi
    lại là an
    toàn. Còn timeout hay đứt mạng thì tin có thể đã tới nơi - gửi lại là nhân đôi tin trước mặt người dùng.

    Dấu hiệu: zca-js gắn ``code`` dạng số cho lỗi do máy chủ trả về (``ZaloApiError``), lỗi mạng thì không có.
    The bridge keeps that rule: ``ZaloBridgeError.code`` is set only for ``zalo_rejected``.
    """
    code = getattr(err, "code", None)
    return isinstance(code, int) and not isinstance(code, bool)


def _send_one(
    enqueue_send: EnqueueSend,
    target: ReplyTarget,
    text: str,
    styles: Sequence[TextStyle] = (),
    quote: QuoteRef | None = None,
) -> Awaitable[object]:
    """Gửi 1 tin qua hàng đợi của thread (giữ thứ tự + delay ngẫu nhiên)."""
    return enqueue_send(target.thread_key, lambda: target.gui_mot_doan(DoanCanGui(text, styles, quote)))


async def _send_one_co_duong_lui(
    enqueue_send: EnqueueSend,
    target: ReplyTarget,
    text: str,
    styles: Sequence[TextStyle],
    quote: QuoteRef | None = None,
) -> object:
    """Gửi một đoạn; bị máy chủ từ chối thì thử lại đúng MỘT lần, bỏ định dạng.

    Vì sao cần: 2026-08-05 một câu trả lời có tiêu đề kèm in đậm sinh ra hai span ``b`` chồng nhau, Zalo
    trả mã
    112 và người dùng mất trọn câu trả lời sau 8 lượt tra web. ``chuan_hoa_styles`` đã bịt đúng ca đó,
    nhưng luật
    kiểm của Zalo là hộp đen - không có cách nào liệt kê cho đủ. Nên thay vì đoán cho hết, hạ mức hậu
    quả: tổ hợp
    style lạ chỉ còn làm tin NHẠT ĐI, không làm mất nội dung.

    Chỉ thử lại khi thật sự CÓ thứ để bỏ (style hoặc trích dẫn) - không thì lần hai y hệt lần đầu và chỉ
    tổ nhân
    đôi một lời gọi API không chính thức.

    Lần thử lại bỏ CẢ HAI. Không cố đoán bên nào là thủ phạm: ở nhánh này mục tiêu duy nhất còn lại là chữ TỚI
    NƠI, mà mỗi lần đoán sai là thêm một lời gọi nữa. Trích dẫn cũng là ứng viên thật chứ không phải bịa
    - có nó
    thì zca-js gọi sang endpoint ``.../quote`` khác hẳn, và phần ``qmsg`` cộng thêm vào payload.
    """
    try:
        return await _send_one(enqueue_send, target, text, styles, quote)
    except Exception as err:
        co_cai_de_bo = len(styles) > 0 or quote is not None
        if not co_cai_de_bo or not la_loi_may_chu_tu_choi(err):
            raise

        # WARN chứ không debug: mất định dạng là hỏng thầm lặng, người vận hành phải thấy được để còn lần
        # ra tổ
        # hợp style nào bị Zalo chê.
        log.warning(
            "Zalo từ chối tin - gửi lại dạng chữ trơn, không định dạng và không trích dẫn",
            thread_id=target.thread_id,
            so_style=len(styles),
            co_trich_dan=quote is not None,
            err=err,
        )
        return await _send_one(enqueue_send, target, text)


async def send_reply_in_parts(
    target: ReplyTarget,
    text: str,
    styles: Sequence[TextStyle] = (),
    *,
    enqueue_send: EnqueueSend | None = None,
) -> ReplyResult:
    """Cắt (nếu cần) rồi gửi lần lượt. Một tin hỏng thì dừng luôn phần còn lại - gửi tiếp các đoạn sau sẽ
    ra một
    câu trả lời thủng lỗ chỗ, khó đọc hơn là dừng và báo lỗi.

    ``styles`` tính trên TOÀN VĂN nên phải chẻ theo đúng chỗ cắt - việc đó nằm ở
    ``split_styled_message``, không
    tự làm ở đây.
    """
    queue = enqueue_send or default_enqueue_send()

    # Kênh không mang định dạng (Bot API) thì `styles` sẽ bị đường gửi vứt ở phút chót. Vứt Ở ĐÂY, TRƯỚC
    # bộ cắt,
    # vì hai lý do:
    #
    # 1. `so_byte_tin` cộng cả JSON của `styles` vào ngân sách byte - giữ lại là tính tiền cho thứ không
    # bao giờ
    #    đi trên dây, và chẻ thừa tin.
    # 2. `_send_one_co_duong_lui` bên dưới quyết định có thử lại hay không dựa vào `len(styles) > 0`.
    # Trên kênh
    #    bot, gửi lại "không định dạng" là gửi lại Y HỆT (styles vốn đã bị vứt) - tốn thêm một lời gọi API mà
    #    không đổi được gì. Dòng dưới đóng cửa ấy lại bằng lý do tường minh.
    #
    # Đặt ở đây (MỘT chỗ) chứ không ở từng caller (`deliver_chat_reply` và `scheduled_job_send`): hai chỗ
    # là hai
    # cơ hội quên. Chữ đã được BÓC markdown ở tầng trên (`dinh_dang_neu_bat`) nên không mất gì.
    if target.mang_dinh_dang is False:
        styles = ()

    # Trích dẫn ăn vào CÙNG ngân sách byte với chữ của bot, mà bộ cắt không biết gì về nó - phải trừ
    # trước rồi mới
    # cắt. Quá dài thì bỏ hẳn trích dẫn: mất một khối trang trí còn hơn để Zalo chối cả tin.
    trich_dan = trich_dan_trong_ngan_sach(target.quote, get_tuning_int("ZALO_RICH_TEXT_MAX_PAYLOAD_BYTES"))
    if trich_dan.bo_vi_qua_dai:
        log.warning(
            "Tin được trích dẫn quá dài so với ngân sách byte - trả lời không kèm trích dẫn",
            thread_id=target.thread_id,
        )

    parts = chia_theo_ngan_sach_byte(
        TinCoDinhDang(text=text, styles=list(styles)),
        NganSachByteOptions(
            # Trần của KÊNH thắng trần chung khi kênh có khai. Bot API ép cứng 2000 ký tự phía server (đo
            # thật),
            # còn ZALO_MAX_MESSAGE_CHARS chỉnh được tới 4000 - dùng chung một con số thì ai nới cho kênh
            # cá nhân
            # là kênh bot mất trọn câu trả lời vì server chối nguyên tin.
            max_chars=target.tran_ky_tu_mot_tin
            if target.tran_ky_tu_mot_tin is not None
            else get_tuning_int("ZALO_MAX_MESSAGE_CHARS"),
            max_parts=get_tuning_int("ZALO_MAX_MESSAGE_PARTS"),
            max_payload_bytes=trich_dan.tran_con_lai,
        ),
    )

    if not parts:
        return ReplyResult(delivered_text="", sent_parts=0)

    if len(parts) > 1:
        log.info(
            "Câu trả lời dài - cắt thành nhiều tin",
            thread_id=target.thread_id,
            length=len(text),
            parts=len(parts),
        )

    # Bộ cắt có quyền bỏ định dạng của một đoạn khi co hết cỡ vẫn không lọt ngân sách byte. Nhánh đó phải KÊU
    # LÊN: bản đầu làm việc này lặng lẽ, và lỗi chỉ lộ ra vì người dùng nhìn thấy tin đầu phẳng lì - log không
    # hề nhắc gì. Đếm theo CỜ, không theo `len(styles) == 0`: đoạn cuối thường chỉ là văn xuôi nên vốn
    # không có
    # span nào, mà suy ra từ độ dài thì đó là báo động giả.
    doan_mat_dinh_dang = dem_doan_bo_dinh_dang(parts)
    if doan_mat_dinh_dang > 0:
        log.warning(
            "Đoạn quá nặng so với trần byte của Zalo - gửi đoạn đó dạng chữ trơn",
            thread_id=target.thread_id,
            doan_mat_dinh_dang=doan_mat_dinh_dang,
            tong_doan=len(parts),
        )

    delivered: list[str] = []
    for part in parts:
        try:
            # Chỉ đoạn ĐẦU trích dẫn: các đoạn sau là phần nối tiếp của cùng một câu trả lời, trích lại ở mỗi
            # đoạn thì khối trích dẫn lặp đầy màn hình
            await _send_one_co_duong_lui(
                queue, target, part.text, part.styles, trich_dan.quote if not delivered else None
            )
            delivered.append(part.text)
        except Exception as err:
            log.error(
                "Gửi tin thất bại",
                thread_id=target.thread_id,
                part_index=len(delivered) + 1,
                total=len(parts),
                err=err,
            )
            return ReplyResult(delivered_text="\n".join(delivered), sent_parts=len(delivered), error=err)

    return ReplyResult(delivered_text="\n".join(delivered), sent_parts=len(delivered))


# Lần cuối đã báo lỗi cho mỗi (thread + loại lỗi).
#
# Map sống suốt đời process nhưng KHÔNG rò rỉ đáng kể: khóa chỉ sinh ra khi có lỗi thật, và mỗi thread nhiều
# nhất vài loại. A worker process serves one clinic's threads; the dedupe is per process on purpose (a second
# worker may repeat the notice once, which is harmless).
_lan_bao_loi_cuoi: dict[str, float] = {}

# Khoảng lặng giữa hai lần báo CÙNG một loại lỗi cho CÙNG một thread.
#
# Vì sao cần: provider chết 10 phút mà người ta nhắn 5 lần là 5 tin y hệt nhau đổ xuống - vừa phiền vừa làm họ
# tưởng bot hỏng nặng hơn thực tế. Một lần đã nói đủ ý "chờ rồi nhắn lại".
#
# Khóa gồm CẢ loại lỗi, không chỉ thread: "bot chưa cấu hình xong" và "mạng chập" là hai chuyện khác nhau
# và mỗi
# chuyện đáng được nói một lần. Nuốt câu thứ hai vì câu thứ nhất vừa gửi là giấu đúng thông tin người ta cần.
KHOANG_LANG_BAO_LOI_MS = 60_000


async def notify_technical_error(
    target: ReplyTarget,
    loai_loi: str | None = None,
    *,
    enqueue_send: EnqueueSend | None = None,
) -> None:
    """Báo cho người nhắn biết bot đang hỏng. Tự nuốt lỗi: đây đã là đường cứu cánh, hỏng nốt thì chỉ còn cách
    ghi log.

    Bỏ qua nếu vừa báo đúng loại lỗi này cho thread này - xem ``KHOANG_LANG_BAO_LOI_MS``.
    """
    khoa = f"{target.thread_key}:{loai_loi or 'chung'}"
    lan_cuoi = _lan_bao_loi_cuoi.get(khoa)
    bay_gio = monotonic() * 1000
    if lan_cuoi is not None and bay_gio - lan_cuoi < KHOANG_LANG_BAO_LOI_MS:
        log.debug("Vừa báo lỗi này rồi - không gửi lại", thread_id=target.thread_id, loai_loi=loai_loi)
        return
    # Đánh dấu TRƯỚC khi gửi: gửi là việc async, hai lượt hỏng gần nhau có thể cùng đi qua chỗ kiểm ở trên rồi
    # cùng gửi. Đánh dấu sau thì cửa sổ đó vẫn hở.
    _lan_bao_loi_cuoi[khoa] = bay_gio

    try:
        await _send_one(enqueue_send or default_enqueue_send(), target, cau_loi_theo_loai(loai_loi))
    except Exception as err:
        log.error("Không gửi được cả thông báo lỗi", thread_id=target.thread_id, err=err)


def reset_khu_trung_bao_loi() -> None:
    """Xóa bộ nhớ khử trùng - chỉ test dùng, để các ca không ảnh hưởng lẫn nhau."""
    _lan_bao_loi_cuoi.clear()
