# ported from: src/agent/tools/tool-catalog-read.ts
"""The "read" group of the tool catalogue: lookups, no effect outside.

Split from ``tool_catalog`` (the original split by GROUP so no catalog file grows past its size ceiling
when a new tool is added).

Forced deviation: the original read the settings and the knowledge-base bindings from module singletons
(``isSidecarConfigured``, ``nguonCuaAgent``, ``coNguonNao``); here they arrive through ``ToolDeps`` (the
probes are SYNCHRONOUS because ``ToolSpec.available`` is: it runs on every turn and on the Tools page).
"""

from __future__ import annotations

from pema.agent.tools.get_datetime_tool import create_get_datetime_tool
from pema.agent.tools.get_group_info_tool import create_get_group_info_tool
from pema.agent.tools.kb_search_tool import create_kb_search_tool
from pema.agent.tools.read_image_tool import create_read_image_tool
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.web_fetch_tool import create_web_fetch_tool
from pema.agent.tools.web_search_tool import create_web_search_tool
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolScope, ToolSpec


def read_tool_definitions(deps: ToolDeps) -> list[ToolSpec]:
    def _kb_available(scope: ToolScope) -> bool:
        """The agent has no source bound -> searching yields nothing; showing a tool that always answers empty
        only teaches the model to call it for nothing and costs one step. In a REAL AGENT TURN
        ``scope.agent_id`` is always a real id (mandatory in ``ToolScope``) so the branch always asks "sources
        BOUND to this agent".

        The ``GET /admin/tools`` page (account-wide, no specific agent) passes an EMPTY agent id as the
        convention "which agent is not known": then the right question is "does the store have ANY source yet"
        (``any_source``), not "sources of which agent" (every real agent id is non-empty, so the two branches
        never mix).
        """
        if scope.agent_id == "":
            return deps.kb_availability.any_source()
        return deps.kb_availability.agent_has_sources(scope.agent_id)

    def _build_kb(ctx: ToolContext) -> AgentTool:
        return create_kb_search_tool(ctx, deps)

    return [
        ToolSpec(
            key="get_datetime",
            label="Ngày giờ hiện tại",
            description="Cho bot biết chính xác ngày, giờ, thứ trong tuần theo múi giờ Việt Nam",
            group=ToolGroup.READ,
            # Not boasted: users can look at the clock themselves, listing it as a capability only makes the
            # whole list look amateur. The model still calls this tool normally.
            counts_as_capability=False,
            build=lambda _ctx: create_get_datetime_tool(),
        ),
        ToolSpec(
            key="web_search",
            label="Tìm kiếm web",
            description="Tìm thông tin mới trên web theo chuỗi nguồn, DuckDuckGo luôn đứng cuối",
            group=ToolGroup.READ,
            has_settings=True,
            build=lambda _ctx: create_web_search_tool(),
        ),
        ToolSpec(
            key="web_fetch",
            label="Đọc trang web",
            description="Đọc nội dung 1 URL công khai (đã chặn IP nội bộ chống SSRF)",
            group=ToolGroup.READ,
            has_settings=True,
            build=lambda _ctx: create_web_fetch_tool(),
        ),
        ToolSpec(
            key="read_image",
            label="Nhìn kỹ ảnh",
            description=(
                "Hỏi model đọc ảnh (sidecar) một câu cụ thể về ảnh đã nhận - đếm, đọc chữ nhỏ, soi chi tiết"
            ),
            group=ToolGroup.READ,
            # The image-reading settings (vision mode + sidecar) sit in the Settings modal of this very row:
            # gathered in one place instead of a separate Providers page.
            has_settings=True,
            available=lambda _scope: deps.sidecar_configured(),
            unavailable_hint="Bấm Settings để cấu hình model sidecar đọc ảnh",
            # A scheduled turn has no image to look at again
            runs_in_scheduled_turn=False,
            build=lambda ctx: create_read_image_tool(ctx, deps),
        ),
        ToolSpec(
            key="get_group_info",
            label="Thông tin nhóm",
            description="Xem tên nhóm, số thành viên, danh sách thành viên của nhóm hiện tại",
            group=ToolGroup.READ,
            build=lambda ctx: create_get_group_info_tool(ctx),
        ),
        ToolSpec(
            key="kb_search",
            label="Tra kho tri thức",
            description="Tra tài liệu do chủ bot nạp lên (chính sách, bảng giá, hướng dẫn)",
            group=ToolGroup.READ,
            has_settings=False,
            available=_kb_available,
            # I18: the older sentence told the operator to "go to the Knowledge tab to load/assign". That
            # tab only LOADS documents, it has no assignment box (its own subtitle says so). The
            # assignment box is in the Knowledge block RIGHT BELOW this tool list, on the agent edit page:
            # say exactly one place, do not send the operator around.
            unavailable_hint=(
                "Kho tri thức chưa có nguồn nào (nạp ở trang Kho tri thức), hoặc agent này chưa được gán nguồn - "  # noqa: E501
                "tick nguồn ở khối Kho tri thức ngay bên dưới, trên trang Agents"
            ),
            build=_build_kb,
        ),
    ]
