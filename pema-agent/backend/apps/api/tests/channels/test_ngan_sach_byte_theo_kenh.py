# ported from: src/zalo/ngan-sach-byte-theo-kenh.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Kênh KHÔNG mang định dạng thì ``styles`` không được tính vào ngân sách byte.

Bối cảnh: ``so_byte_tin`` cộng cả JSON của ``styles`` vào ngân sách, còn đường gửi của kênh bot thì VỨT ``styles``
đi vì Bot API không hiểu chúng. Nên trên kênh bot, bộ cắt đang tính tiền cho thứ không bao giờ đi trên dây - và chẻ
thừa tin.

The last case of the original chained the Bot channel (``kenhBot``); package C1 owns that one, so the chain here is
a ``ChannelPort`` that declares ``supports_formatting=False`` (what the Bot channel declares) through the real
``reply_target_from_channel``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.channels.pipeline_testing import immediate_enqueue_send
from pema.channels.send_reply_in_parts import (
    DoanCanGui,
    ReplyTarget,
    reply_target_from_channel,
    send_reply_in_parts,
)
from pema.channels.split_styled_message import TinCoDinhDang, so_byte_tin
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import ChannelCapabilities, ChannelKind, TextStyle, ThreadKind
from pema_contracts.testing import FakeChannel

NGAN_SACH_BYTE = 1200


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({"ZALO_RICH_TEXT_MAX_PAYLOAD_BYTES": NGAN_SACH_BYTE}))
    yield
    reset_tuning_provider()


class Rig:
    def __init__(self) -> None:
        self.da_gui: list[DoanCanGui] = []

    def target(self, *, mang_dinh_dang: bool | None = None, nem: BaseException | None = None) -> ReplyTarget:
        async def gui(doan: DoanCanGui) -> object:
            self.da_gui.append(doan)
            if nem is not None:
                raise nem
            return {}

        return ReplyTarget(
            gui_mot_doan=gui,
            tran_ky_tu_mot_tin=2000,
            mang_dinh_dang=mang_dinh_dang,
            thread_key="acc:thread",
            thread_id="thread",
            thread_type=ThreadKind.USER,
        )


def chuoi_thu() -> tuple[str, list[TextStyle]]:
    """Chuỗi + ``styles`` dày đặc span, chọn sao cho:

    byte chữ                     <= ngân sách  (kênh không định dạng: 1 tin)
    byte chữ + byte styles        > ngân sách  (kênh có định dạng: chẻ nhỏ)
    """
    # ~1000 ký tự. PHẢI dài hơn KY_TU_TOI_THIEU (400) một quãng rộng: bộ cắt co trần ký tự dần và dừng ở 400, nên
    # chuỗi ngắn hơn mốc đó không bao giờ chẻ được thêm tin - nó rơi vào nhánh BỎ ĐỊNH DẠNG thay vì nhánh CHẺ NHỎ.
    tu = [f"tuso{i:05d}" for i in range(100)]
    text = " ".join(tu)
    # Chỉ tô 20 từ đầu: đủ để JSON styles vượt phần dư ngân sách (cần > 200 byte) nhưng không nhiều tới mức MỘT
    # NỬA số styles cũng còn vượt.
    styles: list[TextStyle] = []
    vt = 0
    for i, t in enumerate(tu):
        if i < 20:
            styles.append(TextStyle(start=vt, length=len(t), style="b"))
        vt += len(t) + 1
    return text, styles


def kiem_chuan_chuoi_thu() -> tuple[str, list[TextStyle]]:
    """Hằng số KHÔNG đoán: khẳng định đúng hai bất đẳng thức trước khi bất kỳ ca nào dùng tới."""
    text, styles = chuoi_thu()
    byte_chu = so_byte_tin(TinCoDinhDang(text=text, styles=[]))
    byte_ca_hai = so_byte_tin(TinCoDinhDang(text=text, styles=styles))
    assert byte_chu <= NGAN_SACH_BYTE, f"chữ trần {byte_chu} byte đã vượt ngân sách {NGAN_SACH_BYTE}"
    assert byte_ca_hai > NGAN_SACH_BYTE, (
        f"chữ + styles {byte_ca_hai} byte, chưa vượt ngân sách {NGAN_SACH_BYTE}"
    )
    return text, styles


async def test_ngan_sach_byte_theo_kenh_khong_mang_dinh_dang_gui_mot_doan_khong_nhan_styles() -> None:
    """kênh KHÔNG mang định dạng: `guiMotDoan` không nhận styles, chữ vẫn đã bóc markdown"""
    rig = Rig()
    kq = await send_reply_in_parts(
        rig.target(mang_dinh_dang=False),
        "Bảng giá đây anh",
        [TextStyle(start=0, length=8, style="b")],
        enqueue_send=immediate_enqueue_send,
    )

    assert kq.sent_parts == 1
    assert not rig.da_gui[0].styles, (
        "kênh bot nhận styles - Bot API không hiểu, và ngân sách byte đã tính thừa"
    )
    assert "*" not in rig.da_gui[0].text, "chữ phải đã được bóc markdown ở tầng trên"


async def test_ngan_sach_byte_theo_kenh_styles_bi_vut_thi_khong_tinh_vao_ngan_sach_kenh_bot_che_it_tin_hon() -> (
    None
):
    """styles bị vứt thì KHÔNG được tính vào ngân sách byte - kênh bot chẻ ít tin hơn"""
    text, styles = kiem_chuan_chuoi_thu()
    rig = Rig()
    await send_reply_in_parts(rig.target(), text, styles, enqueue_send=immediate_enqueue_send)
    so_tin_kenh_co_dinh_dang = len(rig.da_gui)
    # Chốt lại bằng TỔNG số span giao được: mất span nghĩa là đã rơi vào nhánh bỏ định dạng. KHÔNG khẳng định "mọi
    # đoạn đều còn styles" - đoạn cuối vốn thường là văn xuôi không có span nào.
    tong_span = sum(len(d.styles) for d in rig.da_gui)
    assert tong_span == len(styles), "kênh có định dạng bị BỎ định dạng thay vì chẻ nhỏ - fixture sai"

    rig.da_gui.clear()
    await send_reply_in_parts(
        rig.target(mang_dinh_dang=False), text, styles, enqueue_send=immediate_enqueue_send
    )
    so_tin_kenh_bot = len(rig.da_gui)

    assert so_tin_kenh_co_dinh_dang > 1, (
        f"kênh có định dạng phải bị CHẺ (đang {so_tin_kenh_co_dinh_dang} tin)"
    )
    assert so_tin_kenh_bot == 1, f"kênh bot chẻ {so_tin_kenh_bot} tin cho một đoạn chữ vừa khít ngân sách"


async def test_ngan_sach_byte_theo_kenh_khong_mang_dinh_dang_may_chu_tu_choi_thi_khong_gui_lai_lan_hai() -> (
    None
):
    """kênh KHÔNG mang định dạng: máy chủ từ chối thì KHÔNG gửi lại lần hai"""
    # `_send_one_co_duong_lui` thử lại "không định dạng" khi `len(styles) > 0`. Trên kênh bot, gửi lại là gửi lại Y
    # HỆT (styles vốn đã bị vứt) - tốn thêm một lời gọi API mà không đổi được gì.
    rig = Rig()
    loi = ZaloBridgeError("zalo_rejected", "máy chủ từ chối", code=112)
    kq = await send_reply_in_parts(
        rig.target(mang_dinh_dang=False, nem=loi),
        "một câu ngắn",
        [TextStyle(start=0, length=3, style="b")],
        enqueue_send=immediate_enqueue_send,
    )

    assert kq.sent_parts == 0
    assert len(rig.da_gui) == 1, "đã gửi lại lần hai dù kênh này vốn không mang định dạng"


async def test_ngan_sach_byte_theo_kenh_co_dinh_dang_van_thu_lai_chu_tron_khi_may_chu_tu_choi() -> None:
    """kênh CÓ định dạng vẫn thử lại chữ trơn khi máy chủ từ chối - không hồi quy"""
    # Đối chứng cho ca trên: kênh cá nhân PHẢI có đường lui (mất định dạng còn hơn mất nội dung - lỗi mã 112).
    rig = Rig()
    lan_goi = 0

    async def gui(doan: DoanCanGui) -> object:
        nonlocal lan_goi
        lan_goi += 1
        rig.da_gui.append(doan)
        if lan_goi == 1:
            raise ZaloBridgeError("zalo_rejected", "mã 112", code=112)
        return {}

    muc = ReplyTarget(
        gui_mot_doan=gui, thread_key="acc:thread", thread_id="thread", thread_type=ThreadKind.USER
    )
    kq = await send_reply_in_parts(
        muc, "một câu ngắn", [TextStyle(start=0, length=3, style="b")], enqueue_send=immediate_enqueue_send
    )

    assert kq.sent_parts == 1
    assert lan_goi == 2, "kênh cá nhân mất đường lui 'gửi lại chữ trơn'"
    assert len(rig.da_gui[0].styles) > 0, "lần đầu phải có styles"
    assert len(rig.da_gui[1].styles) == 0, "lần lui phải bỏ styles"


async def test_ngan_sach_byte_theo_kenh_chuoi_that_kenh_khong_dinh_dang_reply_target_send_reply_in_parts() -> (
    None
):
    """chuỗi THẬT: kênh -> reply_target_from_channel -> send_reply_in_parts không mang styles"""
    # Các ca trên dùng target GIẢ nên chúng chỉ chứng minh `send_reply_in_parts` tôn trọng cờ - không chứng minh
    # cờ có được KHAI và có được CHỞ tới nơi. Ca này đi trọn chuỗi thật.
    channel = FakeChannel(
        caps=ChannelCapabilities(
            channel=ChannelKind.ZALO_BOT,
            can_send_proactive=False,
            max_text_length=2000,
            supports_formatting=False,
        )
    )
    muc = reply_target_from_channel(channel, "chat-1", ThreadKind.USER, "acc:chat-1")

    assert muc.mang_dinh_dang is False, "cờ không đi từ kênh tới ReplyTarget"
    assert muc.tran_ky_tu_mot_tin == 2000, "trần ký tự của NỀN TẢNG phải đi theo kênh"
    await send_reply_in_parts(
        muc,
        "Bảng giá đây anh",
        [TextStyle(start=0, length=8, style="b")],
        enqueue_send=immediate_enqueue_send,
    )

    assert [(p.text, tuple(p.styles)) for p in channel.sent] == [("Bảng giá đây anh", ())]


async def test_ngan_sach_byte_theo_kenh_mang_dinh_dang_thieu_la_co_moi_call_site_cu_giu_nguyen_hanh_vi() -> (
    None
):
    """`mangDinhDang` thiếu = CÓ - mọi call site cũ giữ nguyên hành vi"""
    # Cờ là TÙY CHỌN nên mọi `ReplyTarget` viết trước đợt này đều không khai. Điều kiện phải là `is False`.
    rig = Rig()
    await send_reply_in_parts(
        rig.target(),
        "Bảng giá",
        [TextStyle(start=0, length=8, style="b")],
        enqueue_send=immediate_enqueue_send,
    )
    assert len(rig.da_gui[0].styles) == 1, "target không khai cờ mà bị mất styles"
