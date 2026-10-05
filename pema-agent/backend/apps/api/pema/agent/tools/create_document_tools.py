# ported from: src/agent/tools/create-document-tools.ts
"""Tools that create a .docx/.xlsx and SEND it straight to the conversation.

They send by themselves instead of leaving the model to call ``send_file`` next, for 2 reasons: the file
lives in memory/a temp area (``send_file`` only takes the shared-files store or a URL), and splitting it in
2 steps costs one more turn that re-sends the whole conversation. The ``deliver`` pattern of GoClaw, and
the returned sentence must also tell the model not to send again, otherwise it very easily calls
``send_file`` once more and the user receives the file twice.

Safe by construction: the tools take only DATA (title, paragraphs, tables), never code, and never read a
file from disk at the model's request.

Forced deviations:

* the zod ``documentBlockSchema`` / ``sheetSchema`` are nested pydantic discriminated unions in
  ``pema.documents``; here ``blocks`` / ``sheets`` are declared as raw ``list[dict]`` (min 1) and parsed
  INSIDE the handler (``parse_document_blocks`` / ``parse_sheets``), so a bad payload becomes the
  Vietnamese reason of the parser (``ket_qua_loi``) rather than a generic validation message. The REAL
  nested schema is what the provider is shown: ``FunctionTool(parameters=...)`` replaces the property
  schema of ``blocks`` / ``sheets`` with ``document_blocks_json_schema()`` / ``sheets_json_schema()``
  (provider-safe: self-contained, no tuple, string-only enums);
* ``renderDocx`` / ``renderXlsx`` are CPU work and sync in Python: they run in ``asyncio.to_thread``;
* ``withNamedTempFile`` + ``guiFileKemCaption(api, ...)`` become ``gui_file_kem_caption`` on bytes (the
  channel takes the bytes, see ``send_attachment_with_caption``): no temp file is ever written, so the
  original "delete the temp file" test becomes "nothing is written under the data dir";
* ``ctx.ghiNhanDaGui`` is ``ctx.record_sent``; ``apiCaNhan(ctx)`` is inside ``gui_file_kem_caption``;
* the log line does not carry the file name (a free string the user chose), only counts.

Policy: both tools are switched off in ``patient_channel`` by the registry (they are document tools); the
feature itself is intact for ``staff_assistant``.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool, json_schema_of
from pema.agent.tools.send_attachment_with_caption import gui_file_kem_caption
from pema.agent.tools.sent_by_tool_note import ghi_chu_da_gui_file
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import KetQuaLoiTool, ket_qua_loi
from pema.agent.tools.tool_send import thread_key_of
from pema.documents.document_content_schema import (
    ParseFail,
    document_blocks_json_schema,
    parse_document_blocks,
    parse_sheets,
    sheets_json_schema,
)
from pema.documents.document_limits import check_document_limits, check_spreadsheet_limits, safe_file_name
from pema.documents.document_rate_limit import check_document_rate_limit
from pema.documents.render_docx import DocxMeta, render_docx
from pema.documents.render_xlsx import render_xlsx
from pema.shared.logger import create_logger
from pema_contracts.common import JsonObject
from pema_contracts.tools import ToolContext

log = create_logger("create-document")

DELIVERED_NOTE = "Đã tạo và GỬI file cho người dùng rồi. KHÔNG gọi send_file để gửi lại file này."

WORD_DESCRIPTION = (
    "Tạo file Word (.docx) chuẩn văn bản Việt Nam (Times New Roman 13pt) rồi gửi luôn cho người dùng. "
    "Dùng khi người dùng yêu cầu file, hoặc khi nội dung dài/có bảng mà đọc trong chat sẽ rối. "
    "Văn bản hành chính: mở đầu bằng two_columns (cơ quan bên trái, quốc hiệu **CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM** bên phải), "  # noqa: E501
    "dòng địa danh - ngày tháng dùng paragraph align right, kết bằng two_columns (nơi nhận | chức vụ + tên người ký). "  # noqa: E501
    "Nội dung ngắn thì trả lời thẳng, đừng tạo file."
)

EXCEL_DESCRIPTION = (
    "Tạo file Excel (.xlsx) trình bày sẵn đẹp (banner, header nổi, sọc xen kẽ, số liệu tô màu) rồi gửi luôn cho người dùng. "  # noqa: E501
    "Hợp với báo giá, danh sách, bảng số liệu, báo cáo tổng hợp.\n"
    'Ô trong rows: chuỗi, số, hoặc công thức dạng chuỗi "=B2*C2" (nhân 2 ô cùng dòng) / "=SUM(D2:D9)" (cộng 1 cột, đánh số coi header là dòng 1). '  # noqa: E501
    "Dùng công thức cho ô tính toán để người nhận sửa số là tự tính lại.\n"
    "VIẾT ĐẦY ĐỦ như một báo cáo thật, đừng tóm tắt cụt lủn: báo cáo tổng hợp nên tách nhiều sheet "
    "(tổng quan, chi tiết từng mục, số liệu, rủi ro/kết luận, nguồn tham khảo), mỗi sheet có title + subtitle + note, "  # noqa: E501
    "mỗi ô mô tả trọn ý chứ không phải vài chữ. Đã bỏ công tạo file thì nội dung phải đáng để mở ra đọc.\n"
    'MỌI chữ (tên sheet, tên file, header, nội dung) GIỮ NGUYÊN dấu tiếng Việt - viết "Tổng quan" chứ không "Tong quan".'  # noqa: E501
)

BLOCKS_DESCRIPTION = "Nội dung theo thứ tự: heading, paragraph, bullets, table, two_columns"
SHEETS_DESCRIPTION = "Danh sách sheet, mỗi sheet có tên + cột + dòng"


class CreateWordDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    file_name: str = Field(alias="fileName", min_length=1, description='Tên file, vd "bao-gia-thang-7.docx"')
    title: str | None = Field(default=None, description="Tiêu đề canh giữa, đậm, ở đầu trang")
    blocks: list[dict[str, Any]] = Field(min_length=1, description=BLOCKS_DESCRIPTION)
    caption: str | None = Field(default=None, description="Lời nhắn gửi kèm file")


class CreateExcelFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    file_name: str = Field(alias="fileName", min_length=1, description='Tên file, vd "bao-gia.xlsx"')
    sheets: list[dict[str, Any]] = Field(min_length=1, description=SHEETS_DESCRIPTION)
    caption: str | None = Field(default=None, description="Lời nhắn gửi kèm file")


def _parameters_with_nested(
    model: type[BaseModel], key: str, nested: dict[str, Any], description: str
) -> JsonObject:
    """``json_schema_of(model)`` with the raw-dict property ``key`` replaced by the real nested schema
    (keeping the original ``.describe(...)`` text)."""
    schema = json_schema_of(model)
    properties: dict[str, Any] = {**schema["properties"], key: {**nested, "description": description}}
    return {**schema, "properties": properties}


async def _deliver_file(
    ctx: ToolContext, deps: ToolDeps, file_name: str, data: bytes, caption: str | None
) -> str:
    """Build buffer -> send with caption. Returns the sentence the model reads."""
    await gui_file_kem_caption(ctx, deps, filename=file_name, data=data, caption=caption)
    # Into history: this message does NOT pass ``deliver_chat_reply`` so nobody records it on our behalf.
    # Without it the dashboard does not see it, and next turn the bot does not remember sending the file.
    if ctx.record_sent is not None:
        ctx.record_sent(ghi_chu_da_gui_file(file_name, caption))
    log.info(
        "Đã gửi file tự tạo",
        account_id=ctx.account.id,
        thread_id=ctx.message.thread_id,
        bytes=len(data),
    )
    # ``Math.round`` rounds halves up; Python's ``round`` is banker's rounding
    return f"{DELIVERED_NOTE} (tên file: {file_name}, {math.floor(len(data) / 1024 + 0.5)} KB)"


def _guard_failure(err: Exception) -> KetQuaLoiTool:
    """Wrap every error branch into a sentence for the model - nothing is thrown into the agent loop."""
    log.warning("Tạo/gửi file thất bại", err=err)
    return ket_qua_loi(
        f"Không tạo được file ({err}). Nói thật với người dùng và trả lời nội dung trực tiếp trong chat."
    )


def create_word_document_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[CreateWordDocumentInput]:
    async def handler(args: CreateWordDocumentInput) -> object:
        try:
            parsed = parse_document_blocks(args.blocks)
            if isinstance(parsed, ParseFail):
                return ket_qua_loi(parsed.reason)
            blocks = parsed.value

            limit = check_document_limits(blocks)
            if not limit.ok:
                return ket_qua_loi(limit.reason)

            rate = check_document_rate_limit(thread_key_of(ctx))
            if not rate.ok:
                return ket_qua_loi(rate.reason)

            data = await asyncio.to_thread(render_docx, blocks, DocxMeta(title=args.title))
            return await _deliver_file(ctx, deps, safe_file_name(args.file_name, "docx"), data, args.caption)
        except Exception as err:
            return _guard_failure(err)

    return FunctionTool(
        name="create_word_document",
        description=WORD_DESCRIPTION,
        input_model=CreateWordDocumentInput,
        handler=handler,
        parameters=_parameters_with_nested(
            CreateWordDocumentInput, "blocks", document_blocks_json_schema(), BLOCKS_DESCRIPTION
        ),
    )


def create_excel_file_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[CreateExcelFileInput]:
    async def handler(args: CreateExcelFileInput) -> object:
        try:
            parsed = parse_sheets(args.sheets)
            if isinstance(parsed, ParseFail):
                return ket_qua_loi(parsed.reason)
            sheets = parsed.value

            limit = check_spreadsheet_limits(sheets)
            if not limit.ok:
                return ket_qua_loi(limit.reason)

            rate = check_document_rate_limit(thread_key_of(ctx))
            if not rate.ok:
                return ket_qua_loi(rate.reason)

            data = await asyncio.to_thread(render_xlsx, sheets)
            return await _deliver_file(ctx, deps, safe_file_name(args.file_name, "xlsx"), data, args.caption)
        except Exception as err:
            return _guard_failure(err)

    return FunctionTool(
        name="create_excel_file",
        description=EXCEL_DESCRIPTION,
        input_model=CreateExcelFileInput,
        handler=handler,
        parameters=_parameters_with_nested(
            CreateExcelFileInput, "sheets", sheets_json_schema(), SHEETS_DESCRIPTION
        ),
    )
