# ported from: src/agent/tools/simple-tools.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Four simple tools had NO test before: ``send_file``, ``add_reaction``, ``save_memory``, ``get_group_info``.

They are small so they look obviously right, but all four sit inside the ``ket_qua_loi`` convention (the
loop guard counts from it) and three of them call the channel directly, i.e. the road out to the real
Zalo. Without a test, forgetting to wrap a failing branch, or wrapping a succeeding one by mistake, does
not turn anything red.

BOTH directions are checked for every tool: a failure must be markable, a success must be a bare string.

Forced deviations: the stub ``api`` object of the original is a ``RecordingChannel``
(``pema.agent.tools.testing``) with ``fail_media`` standing for ``apiNem``; the real database of
``setupTestEnv`` is a ``FakeMemory``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pema.agent.tools.add_reaction_tool import create_add_reaction_tool
from pema.agent.tools.get_datetime_tool import create_get_datetime_tool
from pema.agent.tools.get_group_info_tool import create_get_group_info_tool
from pema.agent.tools.save_memory_tool import create_save_memory_tool
from pema.agent.tools.send_file_tool import create_send_file_tool
from pema.agent.tools.testing import (
    FakeMemory,
    FakeMemoryEdit,
    RecordingChannel,
    make_channel,
    make_inbound,
    make_tool_context,
    make_tool_deps,
)
from pema.agent.tools.tool_failure_result_test_helper import ket_qua_thanh_cong, loi_cua_tool
from pema.config.env import get_settings
from pema.shared.safe_remote_download import DownloadOptions, RemoteFile
from pema_contracts.channel import ChannelKind, InboundMessage, ThreadKind
from pema_contracts.common import JsonObject
from pema_contracts.conversation import MemoryEditFailed, MemoryEditOk
from pema_contracts.policy import (
    MemorySource,
    PolicyContext,
    PolicyHooks,
    PolicyProfileKey,
)
from pema_contracts.testing import FakeChannel
from pema_contracts.tools import ToolContext


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("PEMA_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _message(**over: object) -> InboundMessage:
    data: dict[str, object] = {
        "channel": ChannelKind.ZALO_PERSONAL,
        "account_id": "acc-simple",
        "thread_id": "t-simple",
        "sender_id": "u1",
        "msg_id": "m0",
        "cli_msg_id": "c0",
        **over,
    }
    return make_inbound("", **data)  # pyright: ignore[reportArgumentType]


def _ctx(channel: RecordingChannel, **over: object) -> ToolContext:
    return make_tool_context(channel=channel, message=_message(**over))


async def _fake_download(url: str, options: DownloadOptions) -> RemoteFile:
    return RemoteFile(data=b"%PDF-fake", media_type="application/pdf", file_name="bao-gia.pdf")


# ------------------------------------------------------------------------------ send_file


async def test_send_file_missing_file_is_a_marked_failure_and_sends_nothing() -> None:
    """file không có trong kho -> nhánh HỎNG có đánh dấu, KHÔNG gửi gì"""
    channel = make_channel()
    tool = create_send_file_tool(_ctx(channel), make_tool_deps())
    ra = await tool.execute({"source": "khong-co-file-nay.pdf"})
    assert "Không có file" in loi_cua_tool(ra)
    assert channel.media == []


async def test_send_file_blocks_path_traversal_cannot_read_a_real_file_outside_the_store(
    data_dir: Path,
) -> None:
    """chặn path traversal - KHÔNG đọc được file có thật ngoài kho shared-files

    A REAL file outside the store must exist to measure it (the first version of the original case used a
    path that did not exist, so both directions answered "no such file" and removing ``basename`` kept it
    green). ``data/`` holds the encrypted Zalo cookie and the DB: reading an arbitrary file there and
    sending it into the chat is a real leak, and the source is decided by the model, which reads messages
    from strangers."""
    (data_dir / "bi-mat.txt").write_text("NOI DUNG BI MAT", encoding="utf-8")
    channel = make_channel()
    tool = create_send_file_tool(_ctx(channel), make_tool_deps())
    ra = await tool.execute({"source": "../bi-mat.txt"})
    assert len(loi_cua_tool(ra)) > 0, "phải từ chối - basename là hàng rào duy nhất ở đây"
    assert channel.media == [], "TUYỆT ĐỐI không được gửi file ngoài kho"


async def test_send_file_channel_raises_is_caught_as_a_marked_failure_not_thrown_into_the_loop() -> None:
    """api ném -> bắt lại thành nhánh hỏng, KHÔNG ném ra agent loop"""
    channel = make_channel(fail_media=RuntimeError("Zalo từ chối"))
    tool = create_send_file_tool(_ctx(channel), make_tool_deps(), _fake_download)
    ra = await tool.execute({"source": "http://example.invalid/x"})
    assert len(loi_cua_tool(ra)) > 0


async def test_send_file_sends_a_file_from_the_store_and_records_history(data_dir: Path) -> None:
    """gửi được file trong kho -> chuỗi trần, file tới kênh, và history được ghi (ca bổ sung cho Python)"""
    store = data_dir / "shared-files"
    store.mkdir()
    (store / "bao-gia.pdf").write_bytes(b"%PDF-1")
    channel = make_channel()
    recorded: list[str] = []
    ctx = make_tool_context(channel=channel, message=_message(), record_sent=recorded.append)
    tool = create_send_file_tool(ctx, make_tool_deps())
    ra = await tool.execute({"source": "bao-gia.pdf", "caption": "Báo giá **tháng 8**"})
    assert "Đã gửi file" in ket_qua_thanh_cong(ra)
    assert channel.media[0].filename == "bao-gia.pdf"
    assert channel.media[0].caption == "Báo giá tháng 8"
    assert recorded == ["Báo giá **tháng 8** [đã gửi file: bao-gia.pdf]"]  # history keeps the raw caption


# ------------------------------------------------------------------------------ add_reaction


async def test_add_reaction_missing_msg_id_is_a_marked_failure() -> None:
    """thiếu msgId -> nhánh HỎNG (lượt theo lịch không có tin thật để thả vào)"""
    channel = make_channel()
    ctx = make_tool_context(channel=channel, message=make_inbound("x", msg_id=""))
    ra = await create_add_reaction_tool(ctx).execute({"reaction": "heart"})
    assert "msgId" in loi_cua_tool(ra)
    assert channel.reactions == []


async def test_add_reaction_success_is_a_bare_string_and_calls_the_channel() -> None:
    """thả được -> chuỗi trần, và CÓ gọi api"""
    channel = make_channel()
    ra = await create_add_reaction_tool(_ctx(channel)).execute({"reaction": "haha"})
    assert "Đã thả reaction" in ket_qua_thanh_cong(ra)
    assert channel.reactions == [("m0", "haha")]


async def test_add_reaction_channel_raises_is_a_marked_failure() -> None:
    """api ném -> nhánh hỏng có đánh dấu"""
    channel = make_channel(fail_media=RuntimeError("rate limit"))
    ra = await create_add_reaction_tool(_ctx(channel)).execute({"reaction": "like"})
    assert "rate limit" in loi_cua_tool(ra)


async def test_add_reaction_channel_without_the_ability_is_a_marked_failure() -> None:
    """kênh không có năng lực reaction (Bot API) -> nhánh hỏng, không ném (ca bổ sung cho Python)"""
    channel = FakeChannel(caps=make_channel().caps)
    ctx = make_tool_context(channel=channel, message=_message())
    ra = await create_add_reaction_tool(ctx).execute({"reaction": "like"})
    assert "không hỗ trợ" in loi_cua_tool(ra)


# ------------------------------------------------------------------------------ save_memory


async def test_save_memory_saves_a_fact_about_the_sender_and_it_reaches_the_store() -> None:
    """lưu fact về người nhắn -> chuỗi trần, và fact vào DB thật"""
    memory = FakeMemory()
    deps = make_tool_deps(memory=memory)
    ctx = make_tool_context(channel=make_channel(), message=_message(sender_id="u-nho"))
    ra = await create_save_memory_tool(ctx, deps).execute(
        {"content": "Anh Hải thích cà phê đen, không đường", "about": "sender"}
    )
    assert "Đã ghi nhớ" in ket_qua_thanh_cong(ra)
    assert any("cà phê đen" in f.content and f.subject_id == "u-nho" for f in memory.saved), (
        "fact phải vào kho"
    )


async def test_save_memory_missing_subject_is_a_marked_failure_and_writes_nothing() -> None:
    """thiếu đối tượng để lưu -> nhánh HỎNG, không ghi gì"""
    memory = FakeMemory()
    ctx = make_tool_context(channel=make_channel(), message=_message(sender_id=""))
    ra = await create_save_memory_tool(ctx, make_tool_deps(memory=memory)).execute(
        {"content": "gì đó đủ dài để qua schema", "about": "sender"}
    )
    assert "Không xác định được đối tượng" in loi_cua_tool(ra)
    assert memory.saved == []


async def test_save_memory_empty_action_means_remember_not_an_error() -> None:
    """bỏ trống action = ghi nhớ, không phải lỗi (nhánh mặc định `them`)"""
    memory = FakeMemory()
    ra = await create_save_memory_tool(
        make_tool_context(channel=make_channel(), message=_message()), make_tool_deps(memory=memory)
    ).execute({"content": "Thích trà không đường", "about": "sender"})
    assert "Đã ghi nhớ" in ket_qua_thanh_cong(ra)


async def test_save_memory_duplicate_is_not_a_failure() -> None:
    """điều đã có sẵn không phải lỗi: nói rõ là không ghi thêm bản trùng"""
    memory = FakeMemory()
    tool = create_save_memory_tool(
        make_tool_context(channel=make_channel(), message=_message()), make_tool_deps(memory=memory)
    )
    args: JsonObject = {"content": "Thích trà không đường", "about": "sender"}
    await tool.execute(args)
    ra = await tool.execute(args)
    assert "không ghi thêm bản trùng" in ket_qua_thanh_cong(ra)
    assert len(memory.saved) == 1


async def test_save_memory_edit_and_delete_use_the_fragment_and_explain_a_miss() -> None:
    """sửa/xóa theo đoạn chữ; không khớp thì liệt kê điều đang nhớ để model tự sửa"""
    edit = FakeMemoryEdit(MemoryEditOk(old_content="thích trà"))
    tool = create_save_memory_tool(
        make_tool_context(channel=make_channel(), message=_message()), make_tool_deps(memory_edit=edit)
    )
    ra = await tool.execute(
        {"action": "sua", "doan_chu": "trà", "content": "Thích cà phê", "about": "sender"}
    )
    assert ket_qua_thanh_cong(ra) == 'Đã sửa lại: "thích trà" -> "Thích cà phê"'
    assert edit.calls[0][1].only_group_learned is False

    edit.result = MemoryEditFailed(kind="khong_khop", existing_facts=["thích trà"])
    ra = await tool.execute({"action": "xoa", "doan_chu": "cafe", "about": "sender"})
    assert "- thích trà" in loi_cua_tool(ra)


async def test_save_memory_group_scope_is_narrowed_to_facts_learned_in_the_group() -> None:
    """trong nhóm, sửa/xóa điều về MỘT NGƯỜI chỉ đụng được fact học ngay trong nhóm"""
    edit = FakeMemoryEdit()
    ctx = make_tool_context(
        channel=make_channel(), message=_message(is_group=True, thread_kind=ThreadKind.GROUP)
    )
    tool = create_save_memory_tool(ctx, make_tool_deps(memory_edit=edit))
    await tool.execute({"action": "xoa", "doan_chu": "trà", "about": "sender"})
    await tool.execute({"action": "xoa", "doan_chu": "trà", "about": "thread"})
    assert [c[1].only_group_learned for c in edit.calls] == [True, False]


class _DenyMemoryWrites:
    """A policy that behaves like ``patient_channel``: nothing a patient said may be stored by the agent."""

    def __getattr__(self, name: str) -> object:
        raise AttributeError(name)

    async def allow_memory_write(self, ctx: PolicyContext, source: MemorySource) -> bool:
        return False


async def test_save_memory_policy_can_refuse_every_action_and_nothing_is_stored() -> None:
    """chính sách patient_channel: hook allow_memory_write từ chối thì không ghi gì (ca bổ sung)"""
    memory = FakeMemory()
    deps = make_tool_deps(memory=memory, policy=_DenyMemoryWrites())
    ctx = make_tool_context(
        channel=make_channel(), message=_message(), profile=PolicyProfileKey.PATIENT_CHANNEL
    )
    ra = await create_save_memory_tool(ctx, deps).execute(
        {"content": "Bệnh nhân bị dị ứng thuốc tê", "about": "sender"}
    )
    assert "chưa lưu gì" in loi_cua_tool(ra).lower()
    assert memory.saved == []


# ------------------------------------------------------------------------------ get_group_info


async def test_get_group_info_private_chat_is_a_marked_failure() -> None:
    """chat riêng -> nhánh HỎNG (gọi lặp phải bị bộ chặn đếm)"""
    ra = await create_get_group_info_tool(_ctx(make_channel())).execute({})
    assert "chat riêng" in loi_cua_tool(ra)


def _group_ctx(channel: RecordingChannel) -> ToolContext:
    return _ctx(channel, is_group=True, thread_kind=ThreadKind.GROUP)


async def test_get_group_info_in_a_group_returns_a_bare_string_with_name_and_member_count() -> None:
    """trong nhóm -> chuỗi trần có tên nhóm và số thành viên"""
    channel = make_channel(
        group_info={
            "gridInfoMap": {
                "t-simple": {"name": "Nhóm thử", "totalMember": 3, "memVerList": ["u1_1", "u2_1"]}
            }
        }
    )
    text = ket_qua_thanh_cong(await create_get_group_info_tool(_group_ctx(channel)).execute({}))
    assert "Nhóm thử" in text
    assert "Số thành viên: 3" in text
    assert "u1, u2" in text


async def test_get_group_info_channel_raises_is_a_marked_failure_not_thrown_into_the_loop() -> None:
    """api ném -> nhánh hỏng có đánh dấu, không ném ra agent loop"""
    channel = make_channel(fail_media=RuntimeError("mạng chập"))
    ra = await create_get_group_info_tool(_group_ctx(channel)).execute({})
    assert "mạng chập" in loi_cua_tool(ra)


# ------------------------------------------------------------------------------ get_datetime


async def test_get_datetime_returns_time_weekday_date_and_zone_as_a_bare_string() -> None:
    """get_datetime trả giờ, thứ, ngày và múi giờ theo BOT_TIMEZONE (ca bổ sung cho Python)"""
    text = ket_qua_thanh_cong(await create_get_datetime_tool().execute({}))
    assert text.startswith("Bây giờ là ")
    assert "múi giờ Asia/Ho_Chi_Minh" in text


def test_policy_hooks_protocol_is_satisfied_by_the_permissive_default() -> None:
    """ToolDeps.policy mặc định là PermissivePolicyHooks (hành vi staff_assistant)"""
    deps = make_tool_deps()
    hooks: PolicyHooks = deps.policy
    assert hooks is not None
