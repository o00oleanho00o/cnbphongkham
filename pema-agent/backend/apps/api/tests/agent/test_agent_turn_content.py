# ported from: src/agent/agent-turn-content.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Differences forced by the port: the media store and the description cache are the injected
``TurnContentDeps`` (a dict of ``StoredImage`` and ``FakeConversation``), the vision settings live in an
in-memory ``RuntimeSettingsSnapshot`` of one clinic, and instants are aware datetimes. The case that changed
``process.env.TZ`` is kept as "the label follows ``BOT_TIMEZONE``": Python's ``time.tzset`` does not exist on
every platform and the label never reads the process zone anyway (it converts with an explicit zone).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from pema.agent.agent_turn_content import (
    TurnContentDeps,
    build_current_turn_content,
    build_turn_messages,
    resolve_image_context_mode,
)
from pema.agent.history_to_model_messages import StoredImage, history_to_model_messages
from pema.agent.model_vision_detection import clear_vision_detection_cache
from pema.agent.testing_conversation import FakeConversation
from pema.config import env as env_module
from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    install_runtime_settings,
)
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    bot_time_zone,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.config.runtime_vision_settings import VisionSettingsUpdate, update_vision_settings
from pema_contracts.channel import InboundImage, InboundMessage
from pema_contracts.conversation import StoredMessage
from pema_contracts.testing import FAKE_CLINIC_ID, make_inbound

# A valid 1x1 PNG
PNG_B64 = "iVBORw0KGgoAAAABAAAAAQCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


class Env:
    def __init__(self) -> None:
        self.images: dict[str, StoredImage] = {}
        self.conversation = FakeConversation()
        self.tuning = StaticTuningProvider({})
        self.snapshot = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())

    async def deps(self) -> TurnContentDeps:
        async def download(_url: str) -> StoredImage | None:
            return None

        return TurnContentDeps(
            clinic_id=FAKE_CLINIC_ID,
            load_image=self.images.get,
            download_image=download,
            image_descriptions=self.conversation,
        )

    def write_media(self, rel_path: str) -> str:
        self.images[rel_path] = StoredImage(base64=PNG_B64, media_type="image/png")
        return rel_path


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    for name in (
        "LLM_VISION_MODE",
        "VISION_SIDECAR_BASE_URL",
        "VISION_SIDECAR_MODEL",
        "VISION_SIDECAR_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()
    clear_vision_detection_cache()
    e = Env()
    install_runtime_settings(e.snapshot)
    install_tuning_provider(e.tuning)
    yield e
    reset_tuning_provider()
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()


def msg_with_images(text: str, images: list[InboundImage]) -> InboundMessage:
    return make_inbound(
        text, account_id="acc", thread_id="t1", sender_id="u1", sender_name="Hải", images=images
    )


def msg_tu(sender_name: str, text: str, sent_at: str, is_group: bool = True, **extra: Any) -> InboundMessage:
    """A message without images, with a settable sender name and send time (for the line-building tests)."""
    return make_inbound(
        text,
        account_id="acc",
        thread_id="t1",
        sender_id=f"u-{sender_name}",
        sender_name=sender_name,
        is_group=is_group,
        sent_at=datetime.fromisoformat(sent_at.replace("Z", "+00:00")),
        **extra,
    )


def chu_cua_luot(parts: list[dict[str, Any]]) -> str:
    """The LAST text part of the content: the text ``dong_tin_cua_luot`` builds."""
    return [p for p in parts if p["type"] == "text"][-1]["text"]


def parts_of(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    return value  # type: ignore[return-value]


# ------------------------------------------------------------------------------ build_current_turn_content


async def test_build_current_turn_content_blind_khong_tai_anh_chen_1_ghi_chu_tong_dan_bot_noi_that(
    env: Env,
) -> None:
    """blind: không tải ảnh, chèn 1 ghi chú tổng dặn bot nói thật"""
    parts = await build_current_turn_content(
        [
            msg_with_images(
                "dò giúp em", [InboundImage(url="http://x/0.jpg"), InboundImage(url="http://x/1.jpg")]
            )
        ],
        "blind",
        deps=await env.deps(),
    )
    assert len(parts) == 2, "1 ghi chú ảnh + 1 text chính"
    assert re.search(r"gửi kèm 2 ảnh nhưng bạn KHÔNG xem được", parts[0]["text"])
    assert re.search(r"dò giúp em", parts[1]["text"])


async def test_build_current_turn_content_blind_tin_khong_co_anh_thi_khong_chen_ghi_chu(env: Env) -> None:
    """blind: tin không có ảnh thì không chèn ghi chú"""
    parts = await build_current_turn_content([msg_with_images("chào", [])], "blind", deps=await env.deps())
    assert len(parts) == 1
    assert "chào" in parts[0]["text"]


async def test_build_current_turn_content_describe_mo_ta_trung_cache_text_part_khong_co_pixel(
    env: Env,
) -> None:
    """describe: mô tả trúng cache -> text part, KHÔNG có pixel"""
    rel = env.write_media("media/acc/t1/desc-0.png")
    env.conversation.descriptions[rel] = "vé số Đà Lạt 111222"
    parts = await build_current_turn_content(
        [msg_with_images("dò vé", [InboundImage(url="http://x/a.png", local_path=rel)])],
        "describe",
        deps=await env.deps(),
    )
    assert len([p for p in parts if p["type"] == "file"]) == 0
    assert "Mô tả ảnh người dùng vừa gửi: vé số Đà Lạt 111222" in parts[0]["text"]


async def test_build_current_turn_content_describe_sidecar_khong_mo_ta_duoc_note_loi_trung_thuc(
    env: Env,
) -> None:
    """describe: sidecar không mô tả được -> note lỗi trung thực, không im lặng

    Sidecar not configured + no cache -> ``describe_image`` returns None.
    """
    rel = env.write_media("media/acc/t1/desc-fail-0.png")
    parts = await build_current_turn_content(
        [msg_with_images("dò vé", [InboundImage(url="http://x/b.png", local_path=rel)])],
        "describe",
        deps=await env.deps(),
    )
    assert "hệ thống đọc ảnh đang trục trặc" in parts[0]["text"]


async def test_build_current_turn_content_hybrid_ca_pixel_lan_mo_ta_cung_vao_content(env: Env) -> None:
    """hybrid: CẢ pixel LẪN mô tả cùng vào content"""
    rel = env.write_media("media/acc/t1/hy-0.png")
    env.conversation.descriptions[rel] = "hóa đơn 500k"
    parts = await build_current_turn_content(
        [msg_with_images("xem giúp", [InboundImage(url="http://x/c.png", local_path=rel)])],
        "hybrid",
        deps=await env.deps(),
    )
    assert len([p for p in parts if p["type"] == "file"]) == 1, "pixel phải còn"
    assert any(
        p["type"] == "text" and "Mô tả ảnh người dùng vừa gửi: hóa đơn 500k" in p["text"] for p in parts
    ), "mô tả phải kèm theo"


async def test_build_current_turn_content_hybrid_khong_mo_ta_duoc_thi_van_con_pixel_khong_chen_note_loi(
    env: Env,
) -> None:
    """hybrid: không mô tả được thì vẫn còn pixel, KHÔNG chèn note lỗi"""
    rel = env.write_media("media/acc/t1/hy-1.png")
    parts = await build_current_turn_content(
        [msg_with_images("xem giúp", [InboundImage(url="http://x/d.png", local_path=rel)])],
        "hybrid",
        deps=await env.deps(),
    )
    assert len([p for p in parts if p["type"] == "file"]) == 1
    assert not any(p["type"] == "text" and "trục trặc" in p.get("text", "") for p in parts)


# ------------------------------------------------------------------------- label of the time and the sender
# The message of the RUNNING turn must render exactly like the history: the same time label, the same way of
# pasting the name. A drift between them caused a real bug: see ``user_message_line``.


async def test_build_current_turn_content_nhan_gio_moi_tin_mot_dong_co_nhan_gio_tu_sent_at_cua_chinh_tin_do(
    env: Env,
) -> None:
    """mỗi tin một dòng, có nhãn giờ lấy từ sentAt của CHÍNH tin đó"""
    parts = await build_current_turn_content(
        [msg_tu("Hải", "chào bot", "2026-08-07T17:12:00.000Z", False)], "native", deps=await env.deps()
    )
    assert chu_cua_luot(parts) == "[08/08 00:12] Hải: chào bot"


async def test_build_current_turn_content_nhan_gio_batch_nhieu_nguoi_moi_dong_mang_dung_ten_nguoi_viet(
    env: Env,
) -> None:
    """BATCH NHIỀU NGƯỜI: mỗi dòng mang đúng tên người viết dòng đó"""
    parts = await build_current_turn_content(
        [
            msg_tu("Hải", "bot ơi tra giúp giá vàng", "2026-08-07T17:12:00.000Z"),
            msg_tu("Nam", "cho mình hỏi thêm tỉ giá USD", "2026-08-07T17:12:30.000Z"),
        ],
        "native",
        deps=await env.deps(),
    )
    assert chu_cua_luot(parts) == (
        "[08/08 00:12] Hải: bot ơi tra giúp giá vàng\n[08/08 00:12] Nam: cho mình hỏi thêm tỉ giá USD"
    )


async def test_build_current_turn_content_nhan_gio_loi_cua_nguoi_truoc_khong_bi_gan_cho_nguoi_sau(
    env: Env,
) -> None:
    """lời của người trước KHÔNG bị gán cho người sau

    The old version joined flat then pasted the name of the LAST message: "Nam: bot ơi tra giúp giá
    vàng\\ncho mình hỏi thêm tỉ giá USD", Hải's sentence carrying Nam's name.
    """
    chu = chu_cua_luot(
        await build_current_turn_content(
            [
                msg_tu("Hải", "bot ơi tra giúp giá vàng", "2026-08-07T17:12:00.000Z"),
                msg_tu("Nam", "cho mình hỏi thêm tỉ giá USD", "2026-08-07T17:12:30.000Z"),
            ],
            "native",
            deps=await env.deps(),
        )
    )
    assert "Nam: bot ơi tra giúp giá vàng" not in chu
    assert "Hải: bot ơi tra giúp giá vàng" in chu


async def test_build_current_turn_content_nhan_gio_chat_rieng_cung_co_nhan_gio_va_ten_khop_lich_su(
    env: Env,
) -> None:
    """chat riêng cũng có nhãn giờ và tên - khớp đúng cách lịch sử dựng"""
    sent_at = "2026-08-07T17:12:00.000Z"
    luot = chu_cua_luot(
        await build_current_turn_content(
            [msg_tu("Hải", "chào bot", sent_at, False)], "native", deps=await env.deps()
        )
    )
    # The very same message on the NEXT turn, once it is in the history
    trong_lich_su = history_to_model_messages(
        [
            StoredMessage(
                role="user",
                content="chào bot",
                sender_name="Hải",
                created_at=datetime(2026, 8, 7, 17, 12, tzinfo=UTC),
            )
        ],
        0,
        lambda _path: None,
        bot_time_zone(),
    )[0]["content"]
    assert luot == trong_lich_su, "cùng một tin phải render y hệt ở hai đường"


async def test_build_current_turn_content_nhan_gio_tin_chi_co_anh_van_co_nhan_gio_va_mot_cau_mo_ta(
    env: Env,
) -> None:
    """tin chỉ có ảnh vẫn có nhãn giờ và một câu mô tả, không phải dòng trống"""
    tin = msg_tu("Hải", "", "2026-08-07T17:12:00.000Z", images=[InboundImage(url="http://x/0.jpg")])
    parts = await build_current_turn_content([tin], "blind", deps=await env.deps())
    assert chu_cua_luot(parts) == "[08/08 00:12] Hải: (gửi ảnh, không kèm chữ)"


async def test_build_current_turn_content_nhan_gio_theo_bot_timezone_tren_dashboard_khong_phai_gio_may(
    env: Env,
) -> None:
    """nhãn giờ theo BOT_TIMEZONE trên dashboard, không phải giờ máy chạy bot"""
    deps = await env.deps()
    env.tuning.replace({"BOT_TIMEZONE": "Asia/Tokyo"})
    nhat = chu_cua_luot(
        await build_current_turn_content(
            [msg_tu("Hải", "x", "2026-08-07T17:12:00.000Z", False)], "native", deps=deps
        )
    )
    assert nhat == "[08/08 02:12] Hải: x", "phải theo Tokyo (UTC+9), không theo múi giờ tiến trình"

    env.tuning.replace({"BOT_TIMEZONE": "Asia/Ho_Chi_Minh"})
    viet = chu_cua_luot(
        await build_current_turn_content(
            [msg_tu("Hải", "x", "2026-08-07T17:12:00.000Z", False)], "native", deps=deps
        )
    )
    assert viet == "[08/08 00:12] Hải: x"


# ------------------------------------------------------------------ build_turn_messages: filter own turn


def lich_su(row_id: int, noi_dung: str, **extra: Any) -> StoredMessage:
    return StoredMessage(
        id=row_id,
        role="user",
        content=noi_dung,
        sender_name="Hải",
        created_at=datetime(2026, 8, 7, 17, 12, tzinfo=UTC),
        **extra,
    )


def chu_cua_tin_nhan(messages: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append(content)
        else:
            out.append("\n".join(p["text"] for p in content if p["type"] == "text"))
    return out


async def test_build_turn_messages_loc_dong_lich_su_trung_id_voi_tin_cua_batch_bi_bo_model_khong_doc_hai_lan(
    env: Env,
) -> None:
    """dòng lịch sử trùng id với tin của batch bị bỏ - model không đọc hai lần"""
    tin = msg_tu("Hải", "cho mình bảng giá", "2026-08-07T17:12:00.000Z", False, history_row_id=7)
    built = await build_turn_messages(
        history=[lich_su(5, "câu cũ"), lich_su(7, "cho mình bảng giá")],
        batch=[tin],
        tran_token=0,
        deps=await env.deps(),
    )
    chu = chu_cua_tin_nhan(built.messages)
    assert len([c for c in chu if "cho mình bảng giá" in c]) == 1
    assert any("câu cũ" in c for c in chu), "tin cũ vẫn phải còn"


async def test_build_turn_messages_loc_theo_id_chu_khong_theo_noi_dung_cau_cu_giong_het_van_giu(
    env: Env,
) -> None:
    """lọc theo ID chứ không theo nội dung - câu cũ giống hệt vẫn giữ"""
    tin = msg_tu("Hải", "giá vàng hôm nay", "2026-08-07T17:12:00.000Z", False, history_row_id=9)
    built = await build_turn_messages(
        history=[lich_su(5, "giá vàng hôm nay"), lich_su(9, "giá vàng hôm nay")],
        batch=[tin],
        tran_token=0,
        deps=await env.deps(),
    )
    assert len([c for c in chu_cua_tin_nhan(built.messages) if "giá vàng hôm nay" in c]) == 2, (
        "một lần là câu cũ trong lịch sử, một lần là câu đang hỏi"
    )


async def test_build_turn_messages_loc_batch_chua_co_history_row_id_thi_khong_loc_gi(env: Env) -> None:
    """batch chưa có historyRowId thì KHÔNG lọc gì - giữ nguyên hành vi cũ"""
    tin = msg_tu("Hải", "chào bot", "2026-08-07T17:12:00.000Z", False)
    built = await build_turn_messages(
        history=[lich_su(5, "câu cũ")], batch=[tin], tran_token=0, deps=await env.deps()
    )
    assert len([c for c in chu_cua_tin_nhan(built.messages) if "câu cũ" in c]) == 1


async def test_build_turn_messages_loc_id_bo_qua_loai_tin_dang_cho_khoi_lich_su(env: Env) -> None:
    """`idBoQua` loại tin ĐANG CHỜ khỏi lịch sử - nó sẽ được chèn kèm nhãn tin chen

    Without it the model reads the same request twice: once mixed in the history, once under the label "[a new
    message arrived while you were mid-work]".
    """
    tin = msg_tu("Hải", "soạn giúp bài giảng", "2026-08-07T17:12:00.000Z", False, history_row_id=7)
    built = await build_turn_messages(
        history=[lich_su(7, "soạn giúp bài giảng"), lich_su(8, "à mà xuất ra Word nhé")],
        batch=[tin],
        id_bo_qua=[8],
        tran_token=0,
        deps=await env.deps(),
    )
    chu = chu_cua_tin_nhan(built.messages)
    assert len([c for c in chu if "xuất ra Word" in c]) == 0, "tin đang chờ không thuộc lịch sử lượt này"


async def test_build_turn_messages_loc_buoc_mo_ta_anh_chay_tren_cung_danh_sach_voi_phan_render(
    env: Env,
) -> None:
    """bước mô tả ảnh chạy trên CÙNG danh sách với phần render

    On two different lists the description budget falls on the image of this very turn and the old image is
    never described, while ``describe`` mode also drops the pixels: the line reaches the model as bare text with
    no trace of the image. Silent: no log, no note.
    """
    da_xin_mo_ta: list[list[str]] = []
    cua_batch = lich_su(20, "ảnh của lượt này [gửi kèm 1 ảnh]", images=["media/a/t/moi-0.jpg"])
    cu = lich_su(10, "ảnh cũ [gửi kèm 1 ảnh]", images=["media/a/t/cu-0.jpg"])

    async def mo_ta_truoc(paths: Any) -> None:
        da_xin_mo_ta.append(list(paths))

    await build_turn_messages(
        history=[cu, cua_batch],
        batch=[msg_tu("Hải", "xem giúp", "2026-08-07T17:12:00.000Z", False, history_row_id=20)],
        force_mode="describe",
        tran_token=0,
        deps=await env.deps(),
        mo_ta_truoc=mo_ta_truoc,
    )
    assert da_xin_mo_ta[0] == ["media/a/t/cu-0.jpg"], (
        "ảnh của chính lượt này đã có pixel trong nội dung lượt - xin mô tả cho nó là tiêu mất ngân sách của ảnh cũ"
    )


async def test_build_turn_messages_loc_cat_lai_sau_khi_loc_batch_to_khong_lam_teo_cua_so_lich_su(
    env: Env,
) -> None:
    """CẮT LẠI sau khi lọc: batch to không được làm teo cửa sổ lịch sử

    The most expensive case of the whole fix. ``get_recent_messages`` returns the N NEWEST messages and the batch's
    own are among them: filtering without cutting back shrinks a window of 20 to 15 with a batch of 5, and to 0
    at the ceiling of 32. Silent.
    """
    tran = 20
    so_tin_batch = 5
    # The caller reads with a surplus equal to the batch size, as ``agent_loop`` does
    cu = [lich_su(100 + i, f"tin cũ {i}") for i in range(tran)]
    cua_batch = [lich_su(200 + i, f"câu mới {i}") for i in range(so_tin_batch)]
    batch = [
        msg_tu("Hải", f"câu mới {i}", "2026-08-07T17:12:00.000Z", False, history_row_id=200 + i)
        for i in range(so_tin_batch)
    ]
    built = await build_turn_messages(
        history=[*cu, *cua_batch], batch=batch, tran_lich_su=tran, tran_token=0, deps=await env.deps()
    )
    so_tin_lich_su = len(built.messages) - 1  # minus the last message = the content of this very turn
    assert so_tin_lich_su == tran, f"mong {tran} tin cũ, nhận {so_tin_lich_su}"
    assert any("tin cũ 0" in c for c in chu_cua_tin_nhan(built.messages)), (
        "tin cũ nhất trong cửa sổ vẫn phải còn"
    )


async def test_build_turn_messages_loc_hut_van_khong_duoc_vuot_tran_cat_bo_tin_cu_nhat_giu_tin_gan_nhat(
    env: Env,
) -> None:
    """lọc HỤT vẫn không được vượt trần - cắt bỏ tin CŨ NHẤT, giữ tin gần nhất

    The caller asks for a surplus by batch size, but not every message has a row in the window just read (not yet
    written, or the row drifted out of the window). Then the filter drops LESS than the surplus and the result
    exceeds the ceiling: cut back, at the OLD end, to keep the newest part.
    """
    tran = 3
    built = await build_turn_messages(
        history=[
            lich_su(1, "cũ nhất"),
            lich_su(2, "cũ nhì"),
            lich_su(3, "giữa"),
            lich_su(4, "gần"),
            lich_su(5, "của lượt"),
        ],
        # Only ONE of the two ids asked for as surplus is really in the window
        batch=[msg_tu("Hải", "câu đang hỏi", "2026-08-07T17:12:00.000Z", False, history_row_id=5)],
        id_bo_qua=[999],
        tran_lich_su=tran,
        tran_token=0,
        deps=await env.deps(),
    )
    chu = chu_cua_tin_nhan(built.messages)
    assert len(built.messages) - 1 == tran, f"mong đúng {tran} tin lịch sử, nhận {len(built.messages) - 1}"
    assert not any("cũ nhất" in c for c in chu), "phải cắt từ đầu CŨ"
    assert any("gần" in c for c in chu), "tin gần nhất phải giữ"


# --------------------------------------------------------------- resolve_image_context_mode + build_turn_messages


async def test_resolve_image_context_mode_mode_off_co_sidecar_describe_khong_sidecar_blind_khong_goi_mang(
    env: Env,
) -> None:
    """mode off: có sidecar -> describe, không sidecar -> blind (không gọi mạng)"""
    await update_vision_settings(
        FAKE_CLINIC_ID,
        VisionSettingsUpdate(
            mode="off",
            sidecar_base_url="https://gemini.test/v1beta/openai",
            sidecar_model="gemini-3.5-flash-lite",
            sidecar_api_key="AIza-x",
        ),
        snapshot=env.snapshot,
    )
    assert await resolve_image_context_mode() == "describe"

    await update_vision_settings(
        FAKE_CLINIC_ID,
        VisionSettingsUpdate(sidecar_base_url="", sidecar_model="", sidecar_api_key=""),
        snapshot=env.snapshot,
    )
    assert await resolve_image_context_mode() == "blind"


async def test_resolve_image_context_mode_force_mode_ep_che_do_cho_reactive_fallback_bo_qua_auto_detect(
    env: Env,
) -> None:
    """forceMode ép chế độ cho reactive fallback, bỏ qua auto-detect"""
    built = await build_turn_messages(
        history=[],
        batch=[msg_with_images("hỏng rồi thử lại", [InboundImage(url="http://x/e.png")])],
        force_mode="blind",
        # 0 = no limit, stated EXPLICITLY. The field is mandatory on purpose so forgetting it is a type error
        # and not a silently disabled budget.
        tran_token=0,
        deps=await env.deps(),
    )
    assert built.image_mode == "blind"
    last = parts_of(built.messages[-1]["content"])
    assert any("KHÔNG xem được" in p.get("text", "") for p in last)
