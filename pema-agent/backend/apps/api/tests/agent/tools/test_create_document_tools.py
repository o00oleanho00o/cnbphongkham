# ported from: src/agent/tools/create-document-tools.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviations:

* the stub zca-js ``api`` that captured ``sendMessage`` is a ``RecordingChannel`` (``channel.media``);
  ``sendShouldFail`` is ``make_channel(fail_media=RuntimeError("Zalo từ chối"))``;
* the sent file is read with stdlib ``zipfile`` over the bytes (``read-zip-entry`` is not ported);
* ``DOCUMENT_MAX_PER_HOUR=5`` / ``DOCUMENT_MAX_ROWS=10`` are a static tuning provider; the rate limiter is
  module-level state, reset before every test;
* the original "delete the temp file" test: there is no temp file on this path (the channel takes the
  bytes), so the test asserts that nothing is written under the data dir;
* the original excel test went through the zod ``inputSchema.safeParse``; here the payload goes through
  ``FunctionTool.execute`` (pydantic + ``parse_sheets``), and the advertised ``parameters`` carry the real
  nested schema (an added case).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pema.agent.tools.create_document_tools import create_excel_file_tool, create_word_document_tool
from pema.agent.tools.testing import RecordingChannel, make_channel, make_tool_context, make_tool_deps
from pema.agent.tools.tool_failure_result_test_helper import loi_cua_tool
from pema.config.env import get_settings
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.documents.document_rate_limit import reset_document_rate_limit
from pema_contracts.tools import ToolContext


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    install_tuning_provider(StaticTuningProvider({"DOCUMENT_MAX_PER_HOUR": 5, "DOCUMENT_MAX_ROWS": 10}))
    reset_document_rate_limit()
    yield
    reset_document_rate_limit()
    reset_tuning_provider()
    get_settings.cache_clear()


def _make_ctx(channel: RecordingChannel, recorded: list[str] | None = None) -> ToolContext:
    return make_tool_context(
        channel=channel,
        account_patch={"id": "acc-doc"},
        record_sent=recorded.append if recorded is not None else None,
    )


def _zip_text(data: bytes, entry: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(entry).decode("utf-8")


def _paragraph_block(text: str = "abc") -> dict[str, Any]:
    return {"type": "paragraph", "text": text}


async def test_create_word_document_creates_the_file_sends_to_the_right_thread_clean_name_and_tells_model_not_to_resend() -> (
    None
):
    """tạo file, gửi đúng thread, tên file sạch, và DẶN model đừng gửi lại"""
    channel = make_channel()
    recorded: list[str] = []
    ctx = _make_ctx(channel, recorded)
    tool = create_word_document_tool(ctx, make_tool_deps())

    result = await tool.execute(
        {
            "fileName": "Báo giá tháng 7",
            "title": "Báo giá dịch vụ",
            "blocks": [{"type": "paragraph", "text": "Kính gửi Quý khách"}],
            "caption": "File báo giá đây ạ",
        }
    )

    assert len(channel.media) == 1, "phải gửi đúng 1 file"
    sent = channel.media[0]
    assert sent.filename == "Báo giá tháng 7.docx", "tên file không được dính prefix random"
    assert sent.caption == "File báo giá đây ạ"
    assert sent.thread_id == ctx.message.thread_id
    assert sent.data[:2] == b"PK"

    xml = _zip_text(sent.data, "word/document.xml")
    assert "Báo giá dịch vụ" in xml
    assert "Kính gửi Quý khách" in xml
    # Pattern GoClaw: without the warning the model very easily calls send_file next -> sent twice
    assert isinstance(result, str)
    assert "KHÔNG gọi send_file" in result
    assert recorded == ["File báo giá đây ạ [đã gửi file: Báo giá tháng 7.docx]"], "phải ghi vào history"


async def test_create_word_document_no_temp_file_is_left_behind_data_dir_stays_clean() -> None:
    """xóa file tạm sau khi gửi xong - data/tmp không được để lại rác"""
    channel = make_channel()
    tool = create_word_document_tool(_make_ctx(channel), make_tool_deps())

    await tool.execute({"fileName": "x", "blocks": [_paragraph_block()]})

    assert len(channel.media) == 1
    data_dir = get_settings().data_dir
    leftovers = sorted(p.name for p in data_dir.rglob("*")) if data_dir.exists() else []
    assert leftovers == [], "còn sót file/thư mục tạm"


async def test_create_word_document_over_the_content_limit_returns_a_message_and_does_not_send() -> None:
    """vượt giới hạn nội dung -> trả thông báo, KHÔNG gửi file"""
    channel = make_channel()
    tool = create_word_document_tool(_make_ctx(channel), make_tool_deps())

    result = await tool.execute(
        {
            "fileName": "to",
            "blocks": [{"type": "table", "headers": ["A"], "rows": [["x"] for _ in range(11)]}],
        }
    )

    assert channel.media == []
    assert "11 dòng" in loi_cua_tool(result)
    assert "trần 10" in loi_cua_tool(result)


async def test_create_word_document_send_failure_returns_a_sentence_for_the_model_not_thrown_to_the_loop() -> (
    None
):
    """gửi lỗi -> trả câu cho model, không ném ra agent loop"""
    channel = make_channel(fail_media=RuntimeError("Zalo từ chối"))
    tool = create_word_document_tool(_make_ctx(channel), make_tool_deps())

    result = await tool.execute({"fileName": "x", "blocks": [_paragraph_block()]})

    assert "Không tạo được file (Zalo từ chối)" in loi_cua_tool(result)
    assert "Nói thật với người dùng" in loi_cua_tool(result)


async def test_create_word_document_out_of_hourly_quota_blocks_and_sends_no_more() -> None:
    """hết suất trong giờ -> chặn, không gửi thêm"""
    channel = make_channel()
    ctx = _make_ctx(channel)
    payload: dict[str, Any] = {"fileName": "x", "blocks": [_paragraph_block()]}
    for _ in range(5):
        await create_word_document_tool(ctx, make_tool_deps()).execute(payload)
    assert len(channel.media) == 5

    blocked = await create_word_document_tool(ctx, make_tool_deps()).execute(payload)

    assert len(channel.media) == 5, "không được gửi file thứ 6"
    assert "trần 5" in loi_cua_tool(blocked)


async def test_create_word_document_a_malformed_block_is_reported_by_the_parser_and_nothing_is_sent() -> None:
    """block sai định dạng -> báo lý do của parser (tiếng Việt) cho model, không gửi file (ca bổ sung)"""
    channel = make_channel()
    tool = create_word_document_tool(_make_ctx(channel), make_tool_deps())

    result = await tool.execute({"fileName": "x", "blocks": [{"type": "khong-co-loai-nay"}]})

    assert channel.media == []
    assert "blocks[0]" in loi_cua_tool(result)


async def test_create_excel_file_natural_model_payload_passes_validation_then_creates_the_file() -> None:
    """payload TỰ NHIÊN của model (chuỗi/số/công thức chuỗi) qua được inputSchema rồi tạo file - hồi quy vụ chết trên Zalo"""
    channel = make_channel()
    tool = create_excel_file_tool(_make_ctx(channel), make_tool_deps())
    payload: dict[str, Any] = {
        "fileName": "tong-hop-drama",
        "sheets": [
            {
                "name": "Tổng quan",
                "headers": ["Vụ việc", "Thiệt hại (tỷ)", "Ghi chú"],
                "rows": [
                    ["Vụ kim cương A", 5.5, "đang xét xử"],
                    ["Vụ B", 2, ""],
                    ["Tổng", "=SUM(B2:B3)", ""],
                ],
            }
        ],
    }

    result = await tool.execute(payload)

    assert len(channel.media) == 1, "phải gửi được file"
    sheet = _zip_text(channel.media[0].data, "xl/worksheets/sheet1.xml")
    assert "<f>SUM(B2:B3)</f>" in sheet, "công thức chuỗi phải thành công thức thật"
    assert "<v>7.5</v>" in sheet, "phải kèm giá trị cache 5.5 + 2 = 7.5"
    assert isinstance(result, str)
    assert "KHÔNG gọi send_file" in result


async def test_create_excel_file_formula_with_cached_value_is_created_then_sent() -> None:
    """tạo file có công thức KÈM giá trị cache rồi gửi"""
    channel = make_channel()
    tool = create_excel_file_tool(_make_ctx(channel), make_tool_deps())

    result = await tool.execute(
        {
            "fileName": "bang-gia",
            "sheets": [
                {
                    "name": "Báo giá",
                    "headers": ["Mặt hàng", "SL", "Đơn giá", "Thành tiền"],
                    "rows": [
                        [
                            {"kind": "text", "value": "Bàn phím"},
                            {"kind": "number", "value": 2, "format": "plain"},
                            {"kind": "number", "value": 1500000, "format": "money"},
                            {"kind": "formula", "op": "multiply", "columns": ["B", "C"]},
                        ]
                    ],
                }
            ],
        }
    )

    assert len(channel.media) == 1
    assert channel.media[0].filename == "bang-gia.xlsx"
    sheet = _zip_text(channel.media[0].data, "xl/worksheets/sheet1.xml")
    assert "<f>B2*C2</f>" in sheet, "phải có công thức"
    assert "<v>3000000</v>" in sheet, "phải có giá trị cache để preview hiện số"
    assert isinstance(result, str)
    assert "KHÔNG gọi send_file" in result


async def test_create_excel_file_dangerous_extension_is_forced_to_xlsx() -> None:
    """đuôi file nguy hiểm bị ép về .xlsx"""
    channel = make_channel()
    tool = create_excel_file_tool(_make_ctx(channel), make_tool_deps())

    await tool.execute(
        {
            "fileName": "../../hack.exe",
            "sheets": [{"name": "S", "headers": ["A"], "rows": [[{"kind": "text", "value": "x"}]]}],
        }
    )

    assert len(channel.media) == 1
    name = channel.media[0].filename
    assert name.endswith(".xlsx"), f"tên thật: {name}"
    assert ".." not in name, f"còn .. trong {name}"


async def test_create_excel_file_row_with_wrong_column_count_is_blocked_with_the_sheet_name_and_not_sent() -> (
    None
):
    """dòng lệch số cột -> chặn kèm tên sheet, không gửi"""
    channel = make_channel()
    tool = create_excel_file_tool(_make_ctx(channel), make_tool_deps())

    result = await tool.execute(
        {
            "fileName": "lech",
            "sheets": [
                {"name": "Sai cột", "headers": ["A", "B"], "rows": [[{"kind": "text", "value": "x"}]]}
            ],
        }
    )

    assert channel.media == []
    reason = loi_cua_tool(result)
    assert "Sai cột" in reason
    assert "dòng 1" in reason


def test_create_document_tools_advertise_the_real_nested_schema_in_provider_safe_shape() -> None:
    """schema gửi cho provider mang schema lồng thật của blocks/sheets, gốc là object (ca bổ sung)"""
    deps = make_tool_deps()
    ctx = _make_ctx(make_channel())
    word = create_word_document_tool(ctx, deps)
    excel = create_excel_file_tool(ctx, deps)

    assert word.name == "create_word_document"
    assert excel.name == "create_excel_file"
    for params, key in ((word.parameters, "blocks"), (excel.parameters, "sheets")):
        assert params["type"] == "object"
        prop = params["properties"][key]
        assert prop["type"] == "array"
        assert prop["items"] != {"type": "object"}, "phải là schema lồng thật, không phải dict trần"
        assert "$ref" not in str(prop)
        assert "prefixItems" not in str(prop)
        assert params["required"] == ["fileName", key]
