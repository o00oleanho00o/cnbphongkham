# ported from: src/agent/tools/kb-search-tool.ts
"""Tool cho model tự tra Kho tri thức của agent (nạp bằng TOOL, không tự nhét vào prompt - lý do đầy đủ ở
phase-04-tool-kb-search.md: giữ nguyên khoản đầu tư prompt cache của những lượt không đụng tới KB).

Chỉ có mặt trong schema khi agent đã được gán ít nhất một nguồn (xem ``available`` ở ``tool_catalog_read``)
- bày một tool luôn trả rỗng chỉ dạy model gọi vô ích.

Forced deviations: ``tool({...})`` of the Vercel AI SDK -> ``FunctionTool``; zod -> pydantic;
``timTrongKhoTriThuc({cauHoi, agentId, soLuong})`` (a synchronous SQLite FTS query, package D3) ->
``deps.knowledge.search(ctx.clinic_id, question=..., agent_id=ctx.agent.id, limit=...)`` of the async
``KnowledgeSearch`` port, which returns ``KbHit`` (``tenNguon`` -> ``source_name``, ``tieuDe`` -> ``title``,
``noiDung`` -> ``content``). In the clinic the KB holds procedure / FAQ text, not patient records; the
default-deny binding of sources to the agent stays in D3.

The failing branch tells the model only the exception CLASS name, not ``err.message``: a Postgres driver error
can carry query parameters and rows. The full error goes to the log through the safe serializer, and the
QUESTION is never logged (in the clinic it can be a patient's words); the original logged it.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.kb_pack_result import dong_goi_theo_ngan_sach
from pema.agent.tools.kb_search_tool_description import KB_SEARCH_DESCRIPTION
from pema.agent.tools.khu_gia_mao_nhan_nguon import khu_gia_mao_trong_doan, khu_ngoac_vuong_trong_nhan
from pema.agent.tools.tag_ky_tu_an import loc_ky_tu_an
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.knowledge import KbHit
from pema_contracts.tools import ToolContext

log = create_logger("kb-search")

# ``timTrongKhoTriThuc`` (kb-search.ts) KHÔNG tự kẹp ``soLuong`` - SQLite coi ``LIMIT`` âm là "không giới
# hạn" (xem ``kb-fts-query.ts``). Tầng tool là biên cuối cùng trước khi giá trị này chạm SQL nên PHẢI tự kẹp
# ở đây, không tin giá trị đọc từ cấu hình (hay từ bất kỳ đâu khác) luôn nằm trong khoảng hợp lệ. Khoảng khớp
# min/max của KB_TOP_K ở ``tuning_specs``. (Postgres also treats a negative LIMIT as an error, the clamp
# stays the last border.)
SO_LUONG_MIN = 1
SO_LUONG_MAX = 20


def kep_so_luong(raw: float) -> int:
    # Chỉ NaN mới không phải một con số thật - Infinity vẫn kẹp bình thường (``math.isfinite(inf)`` là False
    # nên KHÔNG dùng nó ở đây, kẻo Infinity bị coi ngang NaN và luôn rơi về tối thiểu).
    if math.isnan(raw):
        return SO_LUONG_MIN
    if math.isinf(raw):  # ``math.trunc(inf)`` raises in Python; JS ``Math.trunc(Infinity)`` is Infinity
        return SO_LUONG_MAX if raw > 0 else SO_LUONG_MIN
    return min(SO_LUONG_MAX, max(SO_LUONG_MIN, math.trunc(raw)))


def dinh_dang_doan(d: KbHit) -> str:
    """Chống giả mạo nhãn nguồn (I13, chi tiết ở ``khu_gia_mao_nhan_nguon``): một tài liệu (hoặc chính TÊN
    NGUỒN/TIÊU ĐỀ của nó) có thể tự viết đúng định dạng ``[Nguồn: ...]`` cùng dải phân cách
    ``\\n\\n---\\n\\n`` để tự gán nội dung độc hại cho một nguồn khác. ``ten_nguon``/``tieu_de`` đi qua
    ĐÚNG pipeline nội dung đoạn nhận (lọc dải Tags rồi khử nhãn/dải phân cách giả), RỒI mới khử ngoặc
    vuông còn sót - lớp phòng thêm hẹp hơn, chạy sau cùng vì nó đổi CẤU TRÚC (ngoặc) chứ không chỉ nội
    dung."""

    def an_toan_hoa(s: str) -> str:
        return khu_ngoac_vuong_trong_nhan(khu_gia_mao_trong_doan(loc_ky_tu_an(s)))

    ten_nguon = an_toan_hoa(d.source_name)
    tieu_de = an_toan_hoa(d.title)
    nhan = f"{ten_nguon} - {tieu_de}" if tieu_de else ten_nguon
    return f"[Nguồn: {nhan}]\n{khu_gia_mao_trong_doan(loc_ky_tu_an(d.content))}"


class KbSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cau_hoi: str = Field(
        min_length=1, description="Câu hỏi hoặc từ khóa cần tra, viết bằng tiếng Việt tự nhiên"
    )


def create_kb_search_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[KbSearchInput]:
    async def handler(args: KbSearchInput) -> object:
        cau_hoi = args.cau_hoi
        try:
            so_luong = kep_so_luong(get_tuning_int("KB_TOP_K"))
            ket_qua = await deps.knowledge.search(
                ctx.clinic_id, question=cau_hoi, agent_id=ctx.agent.id, limit=so_luong
            )

            if len(ket_qua) == 0:
                return ket_qua_loi(
                    f'Không tìm thấy nội dung nào khớp "{cau_hoi}" trong kho tri thức. '
                    "Nói thật là chưa có trong tài liệu, đừng bịa số liệu."
                )

            nguon = f"kho tri thức: {cau_hoi}"
            max_chars = get_tuning_int("KB_MAX_RESULT_CHARS")

            # ĐÓNG GÓI TRƯỚC rồi mới BỌC SAU (I2 - cách cũ bọc trước rồi cắt cả khối đã bọc, nên trần bao
            # gồm luôn phần vỏ, không cách nào chừa chỗ cho nó, và cắt giữa chừng làm hỏng cả nghĩa câu lẫn
            # cấu trúc nhãn).
            #
            # Ngân sách NỘI DUNG = trần trừ phần vỏ - đo phần vỏ CHÍNH XÁC bằng cách bọc thử một placeholder
            # 1 ký tự rồi trừ 1: ``wrap_untrusted_content`` ghép [thẻ mở, 3 dòng dặn dò, dòng trống, NỘI
            # DUNG, thẻ đóng] bằng "\n".join - phần vỏ (mọi phần tử trừ nội dung) có độ dài CỐ ĐỊNH với cùng
            # ``nguon``, không phụ thuộc nội dung thật sẽ đóng gói vào đó.
            vo_len = len(wrap_untrusted_content("x", nguon)) - 1
            ngan_sach_noi_dung = max(0, max_chars - vo_len)
            noi_dung_da_dong_goi = dong_goi_theo_ngan_sach(
                [dinh_dang_doan(d) for d in ket_qua], ngan_sach_noi_dung
            )

            return wrap_untrusted_content(noi_dung_da_dong_goi, nguon)
        except Exception as err:
            reason = type(err).__name__
            log.error("Tool kb_search lỗi", err=err)
            return ket_qua_loi(
                f"Tra kho tri thức thất bại ({reason}). Nói thật với người dùng, đừng bịa số liệu."
            )

    return FunctionTool(
        name="kb_search", description=KB_SEARCH_DESCRIPTION, input_model=KbSearchInput, handler=handler
    )
