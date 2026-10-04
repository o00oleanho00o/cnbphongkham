# ported from: src/zalo/incoming-message-router.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Test cho CỬA VÀO của mọi tin nhắn.

Trọng tâm: tin nào cũng phải để lại dấu vết trong history NGAY LÚC NHẬN, kể cả tin bot không xử lý và tin bị hàng chờ
gộp BỎ vì chạm trần. The allowlist filter, ``record_incoming_message``, the batcher and the anomaly watch are package
C1; the router reaches them through the Protocols of ``incoming_message_router`` and the test plugs fakes that behave
like them (the recorder writes the history exactly like ``ghi_tin_den_vao_history``).
"""

from __future__ import annotations

from uuid import UUID

from pema.channels.pipeline_testing import FakeConversation
from pema.channels.zalo_personal.incoming_message_router import (
    RespondDecision,
    RouterDeps,
    drain_background,
    route_incoming_message,
)
from pema.channels.zalo_personal.message_receipts import drain_pending_receipts
from pema.channels.zalo_personal.testing import FakeZaloApi, make_personal_channel
from pema.channels.zalo_personal.zalo_message_parser import describe_for_history
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import InboundMessage
from pema_contracts.conversation import StoredMessage
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAccountStore, fake_account_config

ACC = "acc-router-test"
SELF = "self-999"
CLINIC: UUID = FAKE_CLINIC_ID
TRAN_TIN_DON = 5
"""Ceiling of the fake batcher (the real one is ``TRAN_TIN_DON`` of ``message-batcher.ts``)."""


class FakeContacts:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None:
        self.seen.append((user_id, display_name))


class FakeThreads:
    def __init__(self) -> None:
        self.activity: list[tuple[str, int, str]] = []

    async def record_thread_activity(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        thread_id: str,
        thread_type: int,
        display_name: str,
        sender_name: str,
    ) -> None:
        self.activity.append((thread_id, thread_type, display_name))

    async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
        return True


class FakeNames:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    async def has_display_name(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
        return thread_id in self.names

    async def set_thread_display_name(
        self, clinic_id: UUID, account_id: str, thread_id: str, name: str
    ) -> None:
        self.names[thread_id] = name


class FakeBatcher:
    def __init__(self, ceiling: int = TRAN_TIN_DON) -> None:
        self.ceiling = ceiling
        self.queued: dict[str, list[InboundMessage]] = {}
        self.dropped: list[InboundMessage] = []

    async def enqueue_message(self, clinic_id: UUID, thread_key: str, msg: InboundMessage) -> bool:
        queue = self.queued.setdefault(thread_key, [])
        if len(queue) >= self.ceiling:
            self.dropped.append(msg)
            return False
        queue.append(msg)
        return True


def respond_all(config: AccountConfig, msg: InboundMessage, bot_enabled: bool) -> RespondDecision:
    return RespondDecision(respond=True)


class Rig:
    def __init__(self, decision: RespondDecision | None = None) -> None:
        self.config = fake_account_config(id=ACC, channel="zalo_personal")  # type: ignore[arg-type]
        self.conversation = FakeConversation()
        self.batcher = FakeBatcher()
        self.contacts = FakeContacts()
        self.threads = FakeThreads()
        self.names = FakeNames()
        self.anomalies: list[str] = []
        self.recorded_order: list[str] = []
        self.channel = make_personal_channel(config=self.config)
        self.api = self.channel.api
        fixed = decision

        def should_respond(config: AccountConfig, msg: InboundMessage, bot_enabled: bool) -> RespondDecision:
            return fixed if fixed is not None else RespondDecision(respond=True)

        async def record_incoming(clinic_id: UUID, msg: InboundMessage, *, luu_anh_ngay: bool) -> int:
            """``ghiTinDenVaoHistory``: write the history at receipt and stamp the row id on the message."""
            row_id = await self.conversation.append_message(
                clinic_id,
                ACC,
                msg.thread_id,
                StoredMessage(
                    role="user",
                    content=describe_for_history(msg),
                    sender_name=msg.sender_name,
                    sender_id=msg.sender_id,
                    created_at=msg.sent_at,
                ),
            )
            msg.history_row_id = row_id
            self.recorded_order.append(msg.msg_id)
            return row_id

        self.deps = RouterDeps(
            accounts=InMemoryAccountStore(self.config),
            contacts=self.contacts,
            threads=self.threads,
            thread_names=self.names,
            should_respond=should_respond,
            record_incoming=record_incoming,
            report_anomalies=lambda account_id, msg: self.anomalies.append(msg.thread_id),
            batcher=self.batcher,
            busy_notifier=None,
            persist_images=None,
            attach_images=None,
        )

    async def route(self, raw: dict[str, object]) -> None:
        await route_incoming_message(self.deps, CLINIC, self.channel, raw, self_id=SELF)
        await drain_background()
        await drain_pending_receipts()

    def history(self, thread_id: str) -> list[str]:
        return [c for _, c in self.conversation.contents(ACC, thread_id)]


def tin_raw(thread_id: str, text: str, msg_id: str, *, group: bool = False) -> dict[str, object]:
    return {
        "threadId": thread_id,
        "type": 1 if group else 0,
        "isSelf": False,
        "data": {
            "content": text,
            "uidFrom": "user-1",
            "dName": "Hải",
            "msgId": msg_id,
            "cliMsgId": f"c-{msg_id}",
            "idTo": SELF,
        },
    }


async def test_route_incoming_message_ghi_lich_su_ngay_luc_nhan_ghi_ngay_khong_doi_luot_chay_xong() -> None:
    """ghi NGAY, không đợi lượt chạy xong"""
    rig = Rig()
    await rig.route(tin_raw("thread-ghi-ngay", "chào bot", "m-don"))

    # Chưa lượt nào chạy - tin phải đã nằm trong lịch sử. Đây là bất biến cho phép lượt chạy song song mà thứ tự
    # vẫn đúng.
    assert rig.history("thread-ghi-ngay") == ["chào bot"]
    assert [m.text for m in rig.batcher.queued[f"{ACC}:thread-ghi-ngay"]] == ["chào bot"]


async def test_route_incoming_message_ghi_lich_su_ngay_luc_nhan_ghi_dung_mot_dong_cho_moi_tin_dung_thu_tu() -> (
    None
):
    """ghi đúng MỘT dòng cho mỗi tin, theo đúng thứ tự người ta gửi"""
    rig = Rig()
    for i, chu in enumerate(["câu một", "câu hai", "câu ba"]):
        await rig.route(tin_raw("thread-thu-tu", chu, f"m-tt-{i}"))

    assert rig.history("thread-thu-tu") == ["câu một", "câu hai", "câu ba"]


async def test_route_incoming_message_ghi_lich_su_ngay_luc_nhan_tin_bi_bo_vi_hang_cho_cham_tran_van_vao_history() -> (
    None
):
    """tin bị bỏ vì hàng chờ chạm trần VẪN vào history - không im lặng nuốt"""
    rig = Rig()
    thread_id = "thread-tran-history"
    so_thua = 3
    tong = TRAN_TIN_DON + so_thua
    for i in range(tong):
        await rig.route(tin_raw(thread_id, f"tin-{i}", f"m{i}"))

    # MỌI tin đều đã vào lịch sử, cả tin lọt batch lẫn tin bị bỏ. Người nhắn đã nhận dấu "đã nhận" nên im lặng nuốt
    # bất kỳ tin nào là kết cục tệ.
    da_ghi = rig.history(thread_id)
    assert len(da_ghi) == tong, f"mong {tong} dòng, nhận {len(da_ghi)}"
    for i in range(so_thua):
        text = f"tin-{TRAN_TIN_DON + i}"
        assert any(text in c for c in da_ghi), f'tin bị bỏ "{text}" phải có trong history'
    assert [m.text for m in rig.batcher.dropped] == [f"tin-{TRAN_TIN_DON + i}" for i in range(so_thua)]


async def test_route_incoming_message_tin_bi_loc_passive_listen_van_duoc_ghi_nhung_khong_xep_hang() -> None:
    """tin bị lọc nhưng `record=True` (passive listen): ghi history, không vào hàng chờ, không có lượt"""
    rig = Rig(RespondDecision(respond=False, record=True, reason="passive"))
    await rig.route(tin_raw("nhom", "đang nói chuyện với nhau", "m1", group=True))

    assert rig.history("nhom") == ["đang nói chuyện với nhau"]
    assert rig.batcher.queued == {}


async def test_route_incoming_message_tin_bi_bo_han_khong_ghi_gi_ca() -> None:
    """tin bị bỏ hẳn (`record=False`): không history, không hàng chờ"""
    rig = Rig(RespondDecision(respond=False, record=False, reason="not allowed"))
    await rig.route(tin_raw("nhom", "người lạ nhắn", "m1", group=True))

    assert rig.history("nhom") == []
    assert rig.batcher.queued == {}


async def test_route_incoming_message_moi_tin_ve_toi_listener_deu_duoc_bao_da_nhan_ke_ca_tin_bi_loc() -> None:
    """ "Đã nhận" cho MỌI tin về tới listener, kể cả tin sắp bị lọc - client Zalo thật cũng báo nhận tự động"""
    rig = Rig(RespondDecision(respond=False, record=False))
    await rig.route(tin_raw("nhom", "người lạ nhắn", "m1", group=True))

    assert isinstance(rig.api, FakeZaloApi)
    delivered = rig.api.delivered
    assert len(delivered) == 1
    assert delivered[0][0] is False, "isSeen=false: đây là 'đã nhận'"


async def test_route_incoming_message_ghi_contact_va_thread_cho_moi_tin() -> None:
    """mọi tin đến (kể cả tin sẽ bị lọc): ghi contact + thread"""
    rig = Rig(RespondDecision(respond=False, record=False))
    await rig.route(tin_raw("thread-1", "chào", "m1"))

    assert rig.contacts.seen == [("user-1", "Hải")]
    assert rig.threads.activity == [("thread-1", 0, "Hải")], "chat riêng lấy tên người gửi làm tên thread"


async def test_route_incoming_message_tin_tu_chinh_minh_khong_ghi_contact() -> None:
    """tin `isSelf` (echo của chính nhận tài khoản) không tạo contact, không báo đã nhận"""
    rig = Rig(RespondDecision(respond=False, record=False))
    raw = tin_raw("thread-1", "chào", "m1")
    raw["isSelf"] = True
    await rig.route(raw)

    assert rig.contacts.seen == []
    assert isinstance(rig.api, FakeZaloApi)
    assert rig.api.delivered == []


async def test_route_incoming_message_payload_khong_co_thread_id_duoc_bao_dong_roi_bo_qua() -> None:
    """tin thiếu threadId bị bỏ qua lặng lẽ ở dòng dưới - phải được báo động ở đây"""
    rig = Rig()
    await rig.route({"data": {"content": "x"}})

    assert rig.anomalies == [""], "reportPayloadAnomalies chạy TRƯỚC mọi nhánh return"
    assert rig.history("") == [], "và không ghi nhầm vào một thread rỗng"


async def test_route_incoming_message_ghi_history_hong_van_xep_hang_de_tra_loi() -> None:
    """bước ghi nay chạy TRƯỚC `enqueue_message`: ghi hỏng là đáng báo động nhưng vẫn phải trả lời người ta"""
    rig = Rig()

    async def broken(clinic_id: UUID, msg: InboundMessage, *, luu_anh_ngay: bool) -> int:
        raise RuntimeError("DB khoá")

    rig.deps.record_incoming = broken
    await rig.route(tin_raw("thread-hong", "chào", "m1"))

    assert [m.text for m in rig.batcher.queued[f"{ACC}:thread-hong"]] == ["chào"]


async def test_route_incoming_message_nhom_lay_ten_nhom_mot_lan_khi_gap_lan_dau() -> None:
    """Lấy tên group 1 lần khi gặp lần đầu, cache vào bảng threads"""
    rig = Rig()
    await rig.route(tin_raw("nhom-9", "chào cả nhà", "m1", group=True))
    await rig.route(tin_raw("nhom-9", "tin thứ hai", "m2", group=True))

    assert rig.names.names == {"nhom-9": "Synthetic group"}
