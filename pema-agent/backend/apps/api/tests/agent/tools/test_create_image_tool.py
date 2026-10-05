# ported from: src/agent/tools/create-image-tool.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviations: the stub zca-js ``api`` of the original that recorded ``sendMessage`` calls is an
``_OrderedChannel`` (a ``RecordingChannel`` that also logs every text, file and generation into ONE event
list, so the ORDER of what the bot does outside can be asserted); the media files are a
``FakeStoredImages`` map; the image settings live in the in-memory ``RuntimeSettingsKv``;
``IMAGE_GEN_MAX_PER_HOUR=2`` is a tuning override."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from pema.agent.tools.create_image_tool import CreateImageInput, create_image_tool
from pema.agent.tools.testing import (
    FakeHistory,
    FakeStoredImages,
    RecordingChannel,
    make_channel,
    make_inbound,
    make_tool_context,
    make_tool_deps,
)
from pema.agent.tools.tool_deps import StoredImage, ToolDeps
from pema.agent.tools.tool_failure_result_test_helper import loi_cua_tool
from pema.config.runtime_image_settings import (
    ImageSettingsUpdate,
    clear_image_settings,
    update_image_settings,
)
from pema.config.runtime_settings_kv import reset_runtime_settings_kv
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.images.image_generation_client import GeneratedImage, GenerateImageParams
from pema.images.image_rate_limit import reset_image_rate_limit
from pema.images.image_retry_policy import ImageGenError
from pema_contracts.channel import ChannelKind, InboundImage, InboundMessage, SendResult, ThreadKind
from pema_contracts.common import JsonObject
from pema_contracts.tools import ToolContext

PNG_BASE64 = "iVBORw0KGgoAAAABAAAAAQCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
JPEG_BYTES = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10])


@dataclass
class Event:
    """Everything the bot does outside, recorded IN ORDER to assert the sequence."""

    kind: str
    msg: str = ""
    file_name: str = ""
    data: bytes = b""
    caption: str = ""
    prompt: str = ""
    has_ref: bool = False
    transparent: bool = False


class _OrderedChannel(RecordingChannel):
    events: list[Event]

    async def send_text(self, thread_id: str, text: str, **kwargs: object) -> SendResult:  # type: ignore[override]
        self.events.append(Event(kind="text", msg=text))
        return await super().send_text(thread_id, text, **kwargs)  # type: ignore[arg-type]

    async def send_image(
        self, thread_id: str, thread_kind: ThreadKind, data: bytes, caption: str
    ) -> SendResult:
        self.events.append(Event(kind="file", file_name=f"anh-x.{_ext_of(data)}", data=data, caption=caption))
        return await super().send_image(thread_id, thread_kind, data, caption)


def _ext_of(data: bytes) -> str:
    return "jpg" if data[:2] == b"\xff\xd8" else "bin"


class _Fixture:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.generate_error: Exception | None = None
        self.generate_error_queue: list[Exception | None] = []
        self.ext = "jpg"

    async def fake_generate(self, params: GenerateImageParams) -> GeneratedImage:
        """Replaces the real provider call: no network, no money."""
        self.events.append(
            Event(
                kind="generate",
                prompt=params.prompt,
                has_ref=params.ref_image is not None,
                transparent=bool(params.transparent_background),
            )
        )
        if self.generate_error_queue:
            loi = self.generate_error_queue.pop(0)
            if loi is not None:
                raise loi
        elif self.generate_error is not None:
            raise self.generate_error
        return GeneratedImage(data=JPEG_BYTES, ext="jpg")  # pyright: ignore[reportArgumentType]


@pytest.fixture
async def fx() -> AsyncIterator[_Fixture]:
    install_tuning_provider(StaticTuningProvider({"IMAGE_GEN_MAX_PER_HOUR": 2}))
    reset_runtime_settings_kv()
    await update_image_settings(
        ImageSettingsUpdate(base_url="https://router.test", model="cx/gpt-5.5-image", api_key="sk-test")
    )
    reset_image_rate_limit()
    yield _Fixture()
    reset_image_rate_limit()
    reset_runtime_settings_kv()
    reset_tuning_provider()


@pytest.fixture(autouse=True)
def _cipher_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "00" * 32)


def _batch_msg(images: list[InboundImage]) -> InboundMessage:
    return make_inbound(
        "vẽ giúp",
        channel=ChannelKind.ZALO_PERSONAL,
        account_id="acc-img",
        thread_id="t-img",
        sender_id="u1",
        msg_id="m1",
        cli_msg_id="c1",
        images=images,
    )


def _make_ctx(
    fx: _Fixture,
    batch: list[InboundMessage] | None = None,
    record_sent: list[str] | None = None,
) -> ToolContext:
    msgs = batch if batch is not None else [_batch_msg([])]
    channel = _OrderedChannel(caps=make_channel().caps)
    channel.events = fx.events
    return make_tool_context(
        channel=channel,
        message=msgs[-1],
        batch=msgs,
        account_patch={"id": "acc-img"},
        record_sent=record_sent.append if record_sent is not None else None,
    )


def _deps(files: dict[str, StoredImage] | None = None) -> ToolDeps:
    return make_tool_deps(history=FakeHistory(), stored_images=FakeStoredImages(files))


def _with_image(fx: _Fixture, name: str) -> tuple[ToolContext, ToolDeps]:
    rel = f"media/acc-img/t-img/{name}.png"
    ctx = _make_ctx(fx, [_batch_msg([InboundImage(url="u", local_path=rel)])])
    return ctx, _deps({rel: StoredImage(base64=PNG_BASE64, media_type="image/png")})


async def _run(fx: _Fixture, ctx: ToolContext, args: JsonObject, deps: ToolDeps | None = None) -> object:
    tool = create_image_tool(ctx, deps or _deps(), fx.fake_generate)
    return await tool.execute(args)


def _kinds(fx: _Fixture) -> list[str]:
    return [e.kind for e in fx.events]


# ------------------------------------------------------------------------------------------- draw new


async def test_create_image_draw_new_notice_then_draw_then_send_in_exactly_that_order(fx: _Fixture) -> None:
    """báo trước RỒI mới vẽ RỒI mới gửi ảnh - đúng thứ tự đó

    Drawing takes ~70 seconds: a notice sent after the drawing is done is pointless.
    """
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "một con mèo đội mũ"})
    assert _kinds(fx) == ["text", "generate", "file"]


async def test_create_image_the_pre_notice_says_it_is_drawing_and_will_take_time(fx: _Fixture) -> None:
    """câu báo trước nói rõ là đang vẽ và sẽ mất thời gian"""
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "con mèo"})
    notice = next(e for e in fx.events if e.kind == "text")
    assert "vẽ" in notice.msg.lower() or "tạo ảnh" in notice.msg.lower()


async def test_create_image_sends_the_image_with_the_extension_the_provider_returned_and_the_caption(
    fx: _Fixture,
) -> None:
    """gửi ảnh với đuôi .jpg đúng như provider trả về, kèm caption"""
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "con mèo", "caption": "Ảnh đây ạ"})
    file = next(e for e in fx.events if e.kind == "file")
    assert file.file_name.endswith(".jpg"), "sai đuôi thì Zalo gửi thành file chứ không thành ẢNH"
    assert file.caption == "Ảnh đây ạ"
    assert file.data == JPEG_BYTES


async def test_create_image_tells_the_model_not_to_resend_or_the_user_gets_the_image_twice(
    fx: _Fixture,
) -> None:
    """DẶN model đừng gửi lại - không dặn thì người dùng nhận ảnh 2 lần"""
    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "con mèo"})
    assert isinstance(result, str)
    assert "KHÔNG gọi send_file" in result


async def test_create_image_transparent_background_is_passed_down_to_the_client(fx: _Fixture) -> None:
    """nền trong suốt truyền xuống client"""
    await _run(
        fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "logo hình tròn", "transparentBackground": True}
    )
    gen = next(e for e in fx.events if e.kind == "generate")
    assert gen.transparent


# ----------------------------------------------------------------------------------- edit an image


async def test_create_image_edit_mode_takes_the_newest_image_as_the_source(fx: _Fixture) -> None:
    """mode sua_anh_da_gui lấy ảnh mới nhất làm ảnh gốc"""
    ctx, deps = _with_image(fx, "m1-0")
    await _run(fx, ctx, {"mode": "sua_anh_da_gui", "prompt": "đổi mũ thành beret đỏ"}, deps)
    gen = next(e for e in fx.events if e.kind == "generate")
    assert gen.has_ref, "thiếu ảnh gốc là thành VẼ MỚI chứ không phải sửa"


async def test_create_image_draw_new_mode_does_not_pull_an_old_image_in_even_if_the_chat_has_one(
    fx: _Fixture,
) -> None:
    """mode ve_moi thì KHÔNG lôi ảnh cũ vào, dù hội thoại đang có ảnh"""
    ctx, deps = _with_image(fx, "m2-0")
    await _run(fx, ctx, {"mode": "ve_moi", "prompt": "vẽ cảnh hoàng hôn"}, deps)
    gen = next(e for e in fx.events if e.kind == "generate")
    assert not gen.has_ref


async def test_create_image_draw_new_with_a_superfluous_image_index_still_draws_new_the_main_shield(
    fx: _Fixture,
) -> None:
    """mode ve_moi kèm imageIndex thừa vẫn vẽ MỚI - đây là lá chắn chính

    The model has a habit of filling every parameter (caught on real Zalo: args {imageIndex: 1} for a
    request to draw a new e-magazine). If imageIndex still decided, it would EDIT the old picture in the
    conversation and the user would get a strange image with nothing saying it is wrong."""
    ctx, deps = _with_image(fx, "m3-0")
    await _run(fx, ctx, {"mode": "ve_moi", "prompt": "vẽ con mèo", "imageIndex": 1}, deps)
    gen = next(e for e in fx.events if e.kind == "generate")
    assert gen.has_ref is False, "mode quyết định, imageIndex thừa bị bỏ qua"


async def test_create_image_edit_request_with_no_image_ever_in_the_chat_still_draws_new_and_does_not_refuse(
    fx: _Fixture,
) -> None:
    """xin sửa ảnh mà hội thoại CHƯA TỪNG có ảnh -> vẫn vẽ mới, không từ chối

    Nobody says "edit the image" before sending one. Refusing makes the model flounder rewriting the
    prompt then give up (really happened: 5 calls, 68k tokens, the user got no image)."""
    result = await _run(fx, _make_ctx(fx), {"mode": "sua_anh_da_gui", "prompt": "vẽ trang e-magazine dọc"})
    gen = next(e for e in fx.events if e.kind == "generate")
    assert gen.has_ref is False, "không có ảnh gốc nên phải vẽ mới"
    assert len([e for e in fx.events if e.kind == "file"]) == 1, "và phải gửi ảnh cho người dùng"
    assert isinstance(result, str)
    assert "KHÔNG gọi send_file" in result


async def test_create_image_the_chat_has_images_but_the_index_is_out_of_range_tells_the_model_without_spending_money(
    fx: _Fixture,
) -> None:
    """hội thoại CÓ ảnh nhưng imageIndex vượt quá -> báo cho model, KHÔNG đốt tiền gọi API"""
    ctx, deps = _with_image(fx, "m9-0")
    result = await _run(fx, ctx, {"mode": "sua_anh_da_gui", "prompt": "sửa ảnh thứ 5", "imageIndex": 5}, deps)
    assert [e for e in fx.events if e.kind == "generate"] == []
    assert "chỉ còn 1 ảnh" in loi_cua_tool(result).lower()


async def test_create_image_an_image_already_swept_from_disk_is_reported_clearly_without_calling_the_api(
    fx: _Fixture,
) -> None:
    """ảnh đã bị dọn khỏi đĩa -> báo rõ, không gọi API"""
    ctx = _make_ctx(fx, [_batch_msg([InboundImage(url="u", local_path="media/acc-img/t-img/da-bi-xoa.png")])])
    result = await _run(fx, ctx, {"mode": "sua_anh_da_gui", "prompt": "sửa"})
    assert [e for e in fx.events if e.kind == "generate"] == []
    loi = loi_cua_tool(result).lower()
    assert "không đọc được" in loi or "đã bị dọn" in loi


# ---------------------------------------------- input schema (through the real model, not execute directly)


def _parse(args: JsonObject) -> CreateImageInput | None:
    try:
        return CreateImageInput.model_validate(args)
    except ValueError:
        return None


def test_create_image_input_schema_mode_is_required_so_the_model_must_choose_consciously() -> None:
    """mode là BẮT BUỘC - thiếu thì schema chặn, model phải chọn có ý thức"""
    # An optional parameter gets filled by inertia; a required one makes it think
    assert _parse({"prompt": "vẽ con mèo"}) is None


def test_create_image_input_schema_an_unknown_mode_is_blocked_only_two_values_are_accepted() -> None:
    """mode lạ bị chặn, chỉ nhận đúng 2 giá trị"""
    assert _parse({"mode": "edit", "prompt": "x"}) is None
    assert _parse({"mode": "ve_moi", "prompt": "x"}) is not None
    assert _parse({"mode": "sua_anh_da_gui", "prompt": "x"}) is not None


def test_create_image_input_schema_an_omitted_image_index_is_exactly_none_not_nan() -> None:
    """bỏ trống imageIndex ra đúng undefined, KHÔNG phải NaN"""
    parsed = _parse({"mode": "ve_moi", "prompt": "vẽ con mèo"})
    assert parsed is not None
    assert parsed.image_index is None


def test_create_image_input_schema_an_empty_prompt_is_blocked_at_the_schema() -> None:
    """prompt rỗng bị chặn ngay ở schema"""
    assert _parse({"mode": "ve_moi", "prompt": ""}) is None


def test_create_image_input_schema_an_image_index_given_as_a_numeric_string_is_still_accepted() -> None:
    """imageIndex dạng chuỗi số vẫn nhận (model hay trả chuỗi)"""
    parsed = _parse({"mode": "sua_anh_da_gui", "prompt": "sửa", "imageIndex": "2"})
    assert parsed is not None
    assert parsed.image_index == 2


# ------------------------------------------------------------------------------------- block and error


async def test_create_image_hitting_the_ceiling_calls_no_api_and_sends_no_pre_notice(fx: _Fixture) -> None:
    """chạm trần thì KHÔNG gọi API và KHÔNG nhắn báo trước"""
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "1"})
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "2"})
    fx.events.clear()

    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "3"})
    assert fx.events == [], "chạm trần mà vẫn nhắn 'đang vẽ' là hứa lèo"
    assert "trần 2" in loi_cua_tool(result)


async def test_create_image_provider_error_returns_a_sentence_for_the_model_and_does_not_raise(
    fx: _Fixture,
) -> None:
    """provider lỗi -> trả câu cho model đọc, KHÔNG throw ra agent loop"""
    fx.generate_error = ImageGenError("API key required for remote API access")
    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "con mèo"})

    assert "API key required" in loi_cua_tool(result)
    assert [e for e in fx.events if e.kind == "file"] == [], "lỗi thì không được gửi file rác"


async def test_create_image_a_provider_error_still_counts_toward_the_ceiling_no_retry_spam_burning_quota(
    fx: _Fixture,
) -> None:
    """provider lỗi vẫn tính vào trần - không cho spam retry đốt quota"""
    fx.generate_error = ImageGenError("quá tải")
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "1"})
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "2"})
    fx.generate_error = None

    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "3"})
    assert "trần 2" in loi_cua_tool(result)


async def test_create_image_not_fully_configured_reports_an_error_instead_of_calling_the_api_with_an_empty_key(
    fx: _Fixture,
) -> None:
    """chưa cấu hình đủ thì báo lỗi thay vì gọi API với key rỗng"""
    await clear_image_settings()
    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "con mèo"})

    assert [e for e in fx.events if e.kind == "generate"] == []
    assert "chưa cấu hình" in loi_cua_tool(result).lower()


# ---------------------------------------------------------------------- a miss draws again once


def _hut_anh() -> ImageGenError:
    return ImageGenError("Codex did not return an image. Account may not be entitled (Plus/Pro required).")


async def test_create_image_miss_first_time_notifies_redraws_then_sends_the_image(fx: _Fixture) -> None:
    """hụt lần đầu -> nhắn báo rồi vẽ lại rồi GỬI ẢNH, người dùng vẫn nhận được ảnh

    Real case of 2026-08-05 (log turnId 166): the provider ran 129.9 seconds then reported "Codex did not
    return an image", the user got exactly one promise then silence. Calling again right after worked 9
    out of 9 times."""
    fx.generate_error_queue = [_hut_anh()]

    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "infographic tiếng Việt"})

    assert _kinds(fx) == ["text", "generate", "text", "generate", "file"], (
        "thứ tự phải là: báo trước - vẽ hụt - báo thử lại - vẽ lại - gửi ảnh"
    )
    assert isinstance(result, str)
    assert "Đã vẽ và GỬI ảnh" in result


async def test_create_image_the_retry_notice_says_plainly_the_first_did_not_come_out_with_a_new_time_frame(
    fx: _Fixture,
) -> None:
    """câu báo thử lại nói THẲNG là lần đầu chưa ra, kèm mốc thời gian mới"""
    fx.generate_error_queue = [_hut_anh()]
    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "poster"})

    texts = [e for e in fx.events if e.kind == "text"]
    assert len(texts) == 2
    assert "chưa ra ảnh" in texts[1].msg.lower(), "ậm ừ 'vẫn đang xử lý' thì lần chờ thứ hai không có lý do"
    assert any(ch.isdigit() for ch in texts[1].msg), (
        "lời hứa 1-3 phút ở đầu lượt đã hết hạn, phải cho mốc mới"
    )


async def test_create_image_the_retry_notice_enters_history_or_the_dashboard_and_the_bot_memory_lose_it(
    fx: _Fixture,
) -> None:
    """câu báo thử lại VÀO history - thiếu thì dashboard và trí nhớ bot đều mất tin đã gửi"""
    fx.generate_error_queue = [_hut_anh()]
    da_ghi: list[str] = []

    await _run(fx, _make_ctx(fx, record_sent=da_ghi), {"mode": "ve_moi", "prompt": "poster"})

    assert len(da_ghi) == 3, "báo trước + báo thử lại + ảnh"
    assert any("chưa ra ảnh" in n.lower() for n in da_ghi), (
        "câu báo thử lại là tin THẬT người ta đọc được, không phải log nội bộ"
    )


async def test_create_image_redraw_does_not_charge_another_slot_punishing_the_user_for_the_provider_is_wrong(
    fx: _Fixture,
) -> None:
    """vẽ lại KHÔNG trừ thêm suất - phạt người dùng vì lỗi provider là sai

    The ceiling in the test is 2. Two turns, each missing once then drawing again fine: counted correctly
    it spends 2 slots, counted per API call it would have spent 4 and the second turn would already have
    been blocked."""
    fx.generate_error_queue = [_hut_anh()]
    dau = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "1"})
    assert isinstance(dau, str)
    assert "Đã vẽ và GỬI ảnh" in dau

    fx.generate_error_queue = [_hut_anh()]
    sau = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "2"})
    assert isinstance(sau, str)
    assert "Đã vẽ và GỬI ảnh" in sau, "lượt thứ hai vẫn phải vẽ được"


async def test_create_image_missing_both_times_tells_the_model_the_truth_and_sends_no_junk_file(
    fx: _Fixture,
) -> None:
    """hụt CẢ HAI lần -> nói thật với model, không gửi file rác"""
    fx.generate_error_queue = [_hut_anh(), _hut_anh()]

    result = await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "poster"})

    assert len([e for e in fx.events if e.kind == "generate"]) == 2, "không được thử tới lần ba"
    assert [e for e in fx.events if e.kind == "file"] == []
    assert "did not return an image" in loi_cua_tool(result)


async def test_create_image_another_class_of_error_neither_redraws_nor_sends_a_retry_notice(
    fx: _Fixture,
) -> None:
    """lỗi KHÁC lớp (sai key) thì KHÔNG vẽ lại và KHÔNG nhắn thử lại"""
    fx.generate_error = ImageGenError("API key required for remote API access")

    await _run(fx, _make_ctx(fx), {"mode": "ve_moi", "prompt": "poster"})

    assert len([e for e in fx.events if e.kind == "generate"]) == 1
    assert len([e for e in fx.events if e.kind == "text"]) == 1, (
        "chỉ còn câu báo trước - hứa 'đang thử lại' khi không thử lại là nói dối"
    )
