# ported from: src/agent/tools/web-search-tool.ts
"""Tìm kiếm web cho agent. Không cần cấu hình gì: DuckDuckGo chạy không key; có BRAVE_SEARCH_API_KEY thì tự
dùng Brave trước (kết quả tốt hơn).

Kết quả web là DỮ LIỆU không tin cậy - persona đã có quy tắc chung, nhưng vẫn nhắc lại trong khung kết quả vì
nội dung trang lạ hoàn toàn có thể chứa chỉ thị prompt injection.

Forced deviations: ``tool({...})`` of the Vercel AI SDK -> ``FunctionTool``; zod -> pydantic. The provider
chain (``search_web``) and its HTTP client are keyword-only injection points so the tests need no network
(the original replaced ``globalThis.fetch``).

Clinic note: every query leaves the infrastructure for a third party. The registry switches this tool off in
the ``patient_channel`` policy profile; the feature itself is kept. The query is never logged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tag_ky_tu_an import loc_ky_tu_an
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.agent.tools.wrap_untrusted_content import wrap_untrusted_content
from pema.config.runtime_tool_settings import get_search_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.shared.web_search_providers import SearchOptions, SearchResult, search_web

type SearchFn = Callable[[str, SearchOptions], Awaitable[list[SearchResult]]]

DESCRIPTION = (
    "Tìm kiếm trên web (tin tức, giá cả, sự kiện, thông tin mới sau thời điểm huấn luyện). Trả về danh sách "
    "tiêu đề + URL + mô tả ngắn. Muốn đọc chi tiết 1 trang thì gọi tiếp tool web_fetch với URL."
)


class WebSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=400, description="Từ khóa tìm kiếm, giữ ngắn gọn")


def create_web_search_tool(
    *, search: SearchFn = search_web, client: httpx.AsyncClient | None = None
) -> FunctionTool[WebSearchInput]:
    async def handler(args: WebSearchInput) -> object:
        query = args.query
        # Cấu hình đọc lại mỗi lượt - đổi provider trên dashboard có hiệu lực ngay. Provider duckduckgo thì
        # không truyền key Brave để chain bỏ qua nó luôn.
        settings = get_search_settings()
        results = await search(
            query,
            SearchOptions(
                max_results=get_tuning_int("WEB_SEARCH_MAX_RESULTS"),
                brave_api_key=settings.brave_api_key if settings.provider == "brave" else None,
                client=client,
            ),
        )

        if len(results) == 0:
            return ket_qua_loi(
                "Không tìm thấy kết quả nào (hoặc dịch vụ tìm kiếm đang lỗi). Thử từ khóa khác."
            )

        lines = [
            f"{i + 1}. {r.title}\n   {r.url}" + (f"\n   {r.snippet}" if r.snippet else "")
            for i, r in enumerate(results)
        ]
        # Tiêu đề và mô tả trong kết quả tìm kiếm cũng do bên ngoài viết ra - một trang đặt tiêu đề thành chỉ
        # thị là đủ để thử điều khiển model. Lọc dải Tags (ASCII smuggling, xem ``tag_ky_tu_an``) TRƯỚC khi
        # bọc - nghiên cứu yêu cầu lọc ở CẢ HAI tầng nạp (KB lẫn web), không chỉ KB.
        return wrap_untrusted_content(loc_ky_tu_an("\n".join(lines)), f"kết quả tìm kiếm: {query}")

    return FunctionTool(
        name="web_search", description=DESCRIPTION, input_model=WebSearchInput, handler=handler
    )
