"""``record_incoming_message`` (``src/zalo/record-incoming-message.ts``, no test file upstream).

The original had no test of its own; the cases below pin the documented behaviour: written at receipt, the row
id stamped on the message, the image fallback, and (new in Pema) the Inbox of record written first and
idempotently.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID

import pytest

from pema.channels.record_incoming_message import (
    InboxRecordError,
    describe_for_history,
    gan_anh_vao_history,
    ghi_tin_den_vao_history,
)
from pema.channels.zalo_bot.testing import FakeConversation, FakeInbox
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.channel import InboundImage, InboundMessage
from pema_contracts.testing import FAKE_CLINIC_ID, make_inbound

CLINIC: UUID = FAKE_CLINIC_ID


async def test_ghi_ngay_va_dong_dau_id_dong_len_chinh_tin() -> None:
    """ghi NGAY lúc nhận và đóng dấu id dòng lên chính tin đó"""
    history = FakeConversation()
    msg = make_inbound("chào", thread_id="t1")
    result = await ghi_tin_den_vao_history(
        clinic_id=CLINIC, account_id="acc-1", msg=msg, luu_anh_ngay=False, history=history
    )
    assert result.history_row_id == 1
    assert msg.history_row_id == 1, (
        "CỐ Ý sửa thẳng object: mọi nơi cầm tin này về sau cần biết dòng nào là của nó"
    )
    row = history.rows[(CLINIC, "acc-1", "t1")][0]
    assert (row.role, row.content, row.sender_id) == ("user", "chào", "user-1")
    assert row.created_at == msg.sent_at, "giờ NGƯỜI TA BẤM GỬI, không phải giờ chạy tới dòng này"


def test_describe_for_history_tin_chi_co_anh_van_phai_co_chu() -> None:
    """tin chỉ có ảnh vẫn phải có chữ, nếu không lượt sau đọc một dòng trống"""
    only_image = make_inbound("", images=[InboundImage(url="https://a.test/1.jpg")])
    assert describe_for_history(only_image) == "[gửi kèm 1 ảnh]"
    assert describe_for_history(make_inbound("", images=[])) == "[ảnh]"
    assert describe_for_history(
        make_inbound("xem giúp", images=[InboundImage(url="https://a.test/1.jpg")])
    ) == ("xem giúp [gửi kèm 1 ảnh]")


async def test_luu_anh_ngay_tai_va_gan_duong_dan_vao_dong_vua_ghi() -> None:
    """luu_anh_ngay: tải ảnh rồi gắn đường dẫn vào dòng vừa ghi"""
    history = FakeConversation()
    msg = make_inbound("xem", images=[InboundImage(url="https://a.test/1.jpg")])

    async def persist(clinic_id: UUID, account_id: str, messages: Sequence[InboundMessage]) -> None:
        for m in messages:
            for image in m.images:
                image.local_path = "media/acc-1/1.jpg"

    await ghi_tin_den_vao_history(
        clinic_id=CLINIC,
        account_id="acc-1",
        msg=msg,
        luu_anh_ngay=True,
        history=history,
        persist_images=persist,
    )
    await doi_cho_den_khi(
        lambda: history.images == {1: ["media/acc-1/1.jpg"]}, WaitOptions(mo_ta="ảnh gắn vào dòng")
    )


async def test_khong_luu_anh_ngay_thi_khong_tai_lan_hai() -> None:
    """luu_anh_ngay=False (sắp có lượt agent tự tải): KHÔNG tải ở đây, tránh tải HAI lần"""
    history = FakeConversation()
    calls = 0

    async def persist(clinic_id: UUID, account_id: str, messages: Sequence[InboundMessage]) -> None:
        nonlocal calls
        calls += 1

    msg = make_inbound("xem", images=[InboundImage(url="https://a.test/1.jpg")])
    await ghi_tin_den_vao_history(
        clinic_id=CLINIC,
        account_id="acc-1",
        msg=msg,
        luu_anh_ngay=False,
        history=history,
        persist_images=persist,
    )
    await asyncio.sleep(0.02)
    assert calls == 0


async def test_gan_anh_bo_qua_tin_chua_co_history_row_id_thay_vi_nem() -> None:
    """ganAnhVaoHistory bỏ qua tin chưa có historyRowId thay vì ném"""
    history = FakeConversation()
    image = InboundImage(url="https://a.test/1.jpg", local_path="media/x.jpg")
    no_row = make_inbound("a", images=[image])
    with_row = make_inbound("b", images=[image], history_row_id=7)
    await gan_anh_vao_history(CLINIC, history, [no_row, with_row])
    assert history.images == {7: ["media/x.jpg"]}


async def test_inbox_ghi_truoc_va_trung_update_id_thi_khong_ghi_history() -> None:
    """(mới) Inbox ghi trước; cùng update_id lần hai -> duplicate, không ghi history thêm"""
    history, inbox = FakeConversation(), FakeInbox()
    msg = make_inbound("chào", update_id="same")
    first = await ghi_tin_den_vao_history(
        clinic_id=CLINIC, account_id="acc-1", msg=msg, luu_anh_ngay=False, history=history, inbox=inbox
    )
    second = await ghi_tin_den_vao_history(
        clinic_id=CLINIC, account_id="acc-1", msg=msg, luu_anh_ngay=False, history=history, inbox=inbox
    )
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.history_row_id is None
    assert len(history.rows[(CLINIC, "acc-1", "thread-1")]) == 1


async def test_loi_inbox_ne_ra_truoc_khi_ghi_history() -> None:
    """(mới) lỗi Inbox -> InboxRecordError, history chưa bị ghi (retry an toàn)"""
    history, inbox = FakeConversation(), FakeInbox()
    inbox.fail = True
    with pytest.raises(InboxRecordError):
        await ghi_tin_den_vao_history(
            clinic_id=CLINIC,
            account_id="acc-1",
            msg=make_inbound("chào"),
            luu_anh_ngay=False,
            history=history,
            inbox=inbox,
        )
    assert history.rows == {}
