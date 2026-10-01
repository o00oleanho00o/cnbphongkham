# ported from: src/agent/tools/read-image-tool.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviation: the media files the original wrote under a temp ``data`` directory are a
``FakeStoredImages`` map (path -> image) behind the ``StoredImageLoader`` port; a missing key stands for a
file the retention job already swept. The SQLite history is a ``FakeHistory``."""

from __future__ import annotations

from pema.agent.tools.read_image_tool import collect_recent_image_paths, create_read_image_tool
from pema.agent.tools.testing import (
    FakeHistory,
    FakeStoredImages,
    FakeVision,
    make_channel,
    make_inbound,
    make_tool_context,
    make_tool_deps,
)
from pema.agent.tools.tool_deps import StoredImage, ToolDeps
from pema.agent.tools.tool_failure_result_test_helper import ket_qua_thanh_cong, loi_cua_tool
from pema_contracts.channel import ChannelKind, InboundImage, InboundMessage
from pema_contracts.common import JsonObject
from pema_contracts.conversation import StoredMessage
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import ToolContext

PNG_BASE64 = "iVBORw0KGgoAAAABAAAAAQCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _batch_msg(thread_id: str, images: list[InboundImage]) -> InboundMessage:
    return make_inbound(
        "hỏi ảnh",
        channel=ChannelKind.ZALO_PERSONAL,
        account_id="acc-ri",
        thread_id=thread_id,
        sender_id="u1",
        msg_id="m1",
        cli_msg_id="c1",
        images=images,
    )


def _make_context(
    thread_id: str,
    batch: list[InboundMessage],
    *,
    profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
) -> ToolContext:
    message = batch[-1] if batch else _batch_msg(thread_id, [])
    return make_tool_context(
        channel=make_channel(),
        message=message,
        batch=batch,
        profile=profile,
        account_patch={"id": "acc-ri"},
    )


def _deps(
    history: list[StoredMessage] | None = None, files: dict[str, StoredImage] | None = None
) -> ToolDeps:
    return make_tool_deps(history=FakeHistory(history), stored_images=FakeStoredImages(files))


def _stored(path: str) -> dict[str, StoredImage]:
    return {path: StoredImage(base64=PNG_BASE64, media_type="image/png")}


async def _run(tool_instance: object, **args: object) -> object:
    payload: JsonObject = {"imageIndex": 1, **args}
    return await tool_instance.execute(payload)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ collectRecentImagePaths


async def test_collect_recent_image_paths_batch_images_come_before_history_newest_first() -> None:
    """ảnh batch hiện tại (chưa vào DB) đứng TRƯỚC ảnh history, mới nhất trước"""
    t = "t-thu-tu"
    history = [StoredMessage(role="user", content="cũ [gửi kèm 1 ảnh]", images=["media/acc-ri/t/cu-0.png"])]
    batch = [_batch_msg(t, [InboundImage(url="http://x/a.png", local_path="media/acc-ri/t/moi-0.png")])]

    paths = await collect_recent_image_paths(_make_context(t, batch), _deps(history))
    assert paths == ["media/acc-ri/t/moi-0.png", "media/acc-ri/t/cu-0.png"]


async def test_collect_recent_image_paths_images_that_failed_to_persist_are_skipped_without_shifting_the_index() -> (
    None
):
    """ảnh batch persist lỗi (không localPath) bị bỏ qua, không làm lệch index"""
    paths = await collect_recent_image_paths(
        _make_context("t-trong", [_batch_msg("t-trong", [InboundImage(url="http://x/fail.png")])]), _deps()
    )
    assert paths == []


async def test_collect_recent_image_paths_an_image_in_both_sources_is_counted_once() -> None:
    """ảnh của batch nằm ở CẢ hai nguồn chỉ được đếm MỘT lần

    Since the user's message is written the moment it is received, the history row of the running batch
    already has the image path: the same picture sits in both ``ctx.batch`` and history. Without removing
    duplicates "image 2" is again image 1 and every old image is pushed back one step: whatever number the
    model chooses misses."""
    t = "t-trung-lap"
    duong = "media/acc-ri/t/dang-chay-0.png"
    history = [
        StoredMessage(role="user", content="cũ [gửi kèm 1 ảnh]", images=["media/acc-ri/t/cu-0.png"]),
        StoredMessage(role="user", content="đang chạy [gửi kèm 1 ảnh]", images=[duong]),
    ]
    batch = [_batch_msg(t, [InboundImage(url="http://x/a.png", local_path=duong)])]

    paths = await collect_recent_image_paths(_make_context(t, batch), _deps(history))
    assert paths == [duong, "media/acc-ri/t/cu-0.png"]


# ------------------------------------------------------------------ read_image tool


async def test_read_image_tool_answers_with_exactly_the_newest_image_and_the_question_reaches_the_sidecar_intact() -> (
    None
):
    """trả lời câu hỏi bằng đúng ảnh mới nhất, câu hỏi đi nguyên vẹn tới sidecar"""
    t = "t-hoi"
    rel_path = f"media/acc-ri/{t}/ca-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/ca.png", local_path=rel_path)])]

    received: dict[str, str] = {}

    async def ask(image: StoredImage, question: str) -> str:
        received["question"] = question
        received["base64"] = image.base64
        return "Có đúng 1 con cá màu vàng, nằm mé phải bể."

    instance = create_read_image_tool(_make_context(t, batch), _deps(files=_stored(rel_path)), ask)

    answer = await _run(instance, question="Đếm số cá màu vàng")
    assert answer == "Có đúng 1 con cá màu vàng, nằm mé phải bể."
    assert received["question"] == "Đếm số cá màu vàng"
    assert received["base64"] == PNG_BASE64, "phải gửi đúng ảnh đã lưu"


async def test_read_image_tool_image_index_selects_an_older_image_from_history() -> None:
    """imageIndex chọn được ảnh cũ hơn trong history"""
    t = "t-index"
    old_path = f"media/acc-ri/{t}/hd-cu-0.png"
    history = [StoredMessage(role="user", content="hóa đơn cũ [gửi kèm 1 ảnh]", images=[old_path])]
    new_path = f"media/acc-ri/{t}/hd-moi-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/n.png", local_path=new_path)])]
    files = {**_stored(old_path), **_stored(new_path)}

    seen: list[str] = []

    async def ask(_image: StoredImage, _question: str) -> str:
        seen.append("called")
        return "ok"

    instance = create_read_image_tool(_make_context(t, batch), _deps(history, files), ask)

    await _run(instance, question="đọc số hóa đơn", imageIndex=2)
    assert len(seen) == 1, "index 2 = ảnh history cũ hơn vẫn gọi được sidecar"


async def test_read_image_tool_no_image_at_all_says_so_plainly_and_does_not_call_the_sidecar() -> None:
    """không có ảnh nào -> nói thẳng, không gọi sidecar"""
    calls: list[int] = []

    async def ask(_image: StoredImage, _question: str) -> str:
        calls.append(1)
        return "x"

    instance = create_read_image_tool(_make_context("t-khong-anh", []), _deps(), ask)
    answer = await _run(instance, question="ảnh gì đây")
    assert "Không có ảnh nào" in loi_cua_tool(answer)
    assert calls == []


async def test_read_image_tool_image_index_beyond_the_number_of_images_reports_the_real_count() -> None:
    """imageIndex vượt số ảnh -> báo số lượng thật"""
    t = "t-vuot"
    rel_path = f"media/acc-ri/{t}/mot-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/1.png", local_path=rel_path)])]

    async def ask(_image: StoredImage, _question: str) -> str:
        return "x"

    instance = create_read_image_tool(_make_context(t, batch), _deps(files=_stored(rel_path)), ask)

    answer = await _run(instance, question="xem ảnh 5", imageIndex=5)
    assert "chỉ còn 1 ảnh" in loi_cua_tool(answer)


async def test_read_image_tool_a_file_already_swept_reports_the_retention_expiry() -> None:
    """file đã bị dọn -> báo hết hạn lưu trữ"""
    t = "t-don"
    batch = [_batch_msg(t, [InboundImage(url="http://x/x.png", local_path=f"media/acc-ri/{t}/da-xoa-0.png")])]

    async def ask(_image: StoredImage, _question: str) -> str:
        return "x"

    instance = create_read_image_tool(_make_context(t, batch), _deps(), ask)
    answer = await _run(instance, question="xem lại")
    assert "đã bị dọn" in loi_cua_tool(answer)


async def test_read_image_tool_sidecar_error_gives_an_honest_message_to_the_model_without_raising() -> None:
    """sidecar lỗi (hết quota) -> thông báo trung thực cho model, không throw"""
    t = "t-loi"
    rel_path = f"media/acc-ri/{t}/err-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/e.png", local_path=rel_path)])]

    async def ask(_image: StoredImage, _question: str) -> str:
        raise RuntimeError("429 quota exceeded")

    instance = create_read_image_tool(_make_context(t, batch), _deps(files=_stored(rel_path)), ask)

    answer = await _run(instance, question="đếm cá")
    loi = loi_cua_tool(answer)
    assert "Hệ thống đọc ảnh đang lỗi" in loi
    assert "429 quota exceeded" in loi
    assert "đừng đoán" in loi


async def test_read_image_tool_defaults_to_the_vision_port_of_the_deps() -> None:
    """không tiêm ask thì dùng deps.vision (ca bổ sung cho Python)"""
    t = "t-port"
    rel_path = f"media/acc-ri/{t}/p-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/p.png", local_path=rel_path)])]
    vision = FakeVision("Thấy một tờ hóa đơn.")
    deps = make_tool_deps(
        history=FakeHistory(), stored_images=FakeStoredImages(_stored(rel_path)), vision=vision
    )

    answer = await _run(create_read_image_tool(_make_context(t, batch), deps), question="đây là gì")
    assert ket_qua_thanh_cong(answer) == "Thấy một tờ hóa đơn."
    assert vision.calls[0][1] == "đây là gì"


async def test_read_image_tool_patient_channel_refuses_to_analyse_a_photo_and_never_reaches_the_sidecar() -> (
    None
):
    """patient_channel: ảnh bệnh nhân chỉ gắn cờ Inbox, KHÔNG phân tích (ca bổ sung theo PLAN-AI01 mục 5)"""
    t = "t-benh-nhan"
    rel_path = f"media/acc-ri/{t}/bn-0.png"
    batch = [_batch_msg(t, [InboundImage(url="http://x/bn.png", local_path=rel_path)])]
    vision = FakeVision("KHÔNG ĐƯỢC GỌI")
    deps = make_tool_deps(
        history=FakeHistory(), stored_images=FakeStoredImages(_stored(rel_path)), vision=vision
    )
    ctx = _make_context(t, batch, profile=PolicyProfileKey.PATIENT_CHANNEL)

    answer = await _run(create_read_image_tool(ctx, deps), question="vết này là gì")

    assert "gắn cờ" in loi_cua_tool(answer)
    assert vision.calls == [], "ảnh của khách không được ra khỏi hạ tầng phòng khám"
