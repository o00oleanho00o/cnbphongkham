# ported from: none (test doubles of the agent engine; stands in for src/agent/tools/tool-registry.ts)
"""Test doubles of package D1, shared by every D1 test and by ``evals/``. Import in tests only.

* ``FakeToolRegistry``: implements ``pema_contracts.tools.ToolRegistry`` over the 15-tool catalogue of
  zalo-agent (key, label, description, group, ``runs_in_scheduled_turn``, ``counts_as_capability``,
  availability rules, copied from ``tool-catalog-action.ts`` / ``tool-catalog-read.ts``) with trivial tool
  bodies. The real registry is package D4's and is not on this branch; the filtering rules here are the
  ones of ``listAvailableTools`` / ``kiemTraKhaDung`` and of ``ToolRegistry.list_available`` in
  ``pema_contracts.tools``, so an engine test that passes here passes against D4's registry (package G
  re-runs the D1 tests against the real one).
* ``make_caps``: a ``ChannelCapabilities`` for tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from pema.config.runtime_tuning_settings import get_tuning
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.common import JsonObject
from pema_contracts.tools import (
    AgentTool,
    ToolAvailability,
    ToolContext,
    ToolGroup,
    ToolScope,
    ToolSpec,
)


def make_caps(**patch: object) -> ChannelCapabilities:
    """Capabilities of a personal-account-like channel (everything allowed) unless patched."""
    data: dict[str, object] = {
        "channel": ChannelKind.ZALO_PERSONAL,
        "can_send_proactive": True,
        "supports_reactions": True,
        "supports_send_file": True,
        "supports_send_image": True,
        "supports_send_video": True,
        "supports_group_info": True,
        "supports_tag_member": True,
        **patch,
    }
    return ChannelCapabilities.model_validate(data)


@dataclass
class FakeTool:
    """A built tool: schema for the model plus a trivial body. ``result`` may be a callable of the args."""

    name: str
    description: str
    result: object | Callable[[JsonObject], object] = "ok"
    parameters: JsonObject = field(
        default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": True}
    )
    calls: list[JsonObject] = field(default_factory=list[JsonObject])

    async def execute(self, args: JsonObject) -> object:
        self.calls.append(args)
        return self.result(args) if callable(self.result) else self.result


def _failure(message: str) -> JsonObject:
    """The machine-readable failed-result shape ``{"ok": False, "loi": str}`` (``ketQuaLoi``)."""
    return {"ok": False, "loi": message}


def _builtin_catalogue(registry: FakeToolRegistry) -> list[ToolSpec]:
    def spec(
        key: str,
        label: str,
        description: str,
        group: ToolGroup,
        *,
        result: object | Callable[[JsonObject], object] = "ok",
        runs_in_scheduled_turn: bool = True,
        counts_as_capability: bool = True,
        has_settings: bool = False,
        available: Callable[[ToolScope], bool] | None = None,
        unavailable_hint: str | None = None,
    ) -> ToolSpec:
        def build(ctx: ToolContext) -> AgentTool:
            tool = FakeTool(name=key, description=description, result=result)
            registry.built.setdefault(key, []).append(tool)
            return tool

        return ToolSpec(
            key=key,
            label=label,
            description=description,
            group=group,
            build=build,
            has_settings=has_settings,
            available=available,
            unavailable_hint=unavailable_hint,
            counts_as_capability=counts_as_capability,
            runs_in_scheduled_turn=runs_in_scheduled_turn,
        )

    read: ToolGroup = ToolGroup.READ
    action: ToolGroup = ToolGroup.ACTION
    return [
        spec(
            "get_datetime",
            "Ngày giờ hiện tại",
            "Cho bot biết chính xác ngày, giờ, thứ trong tuần theo múi giờ Việt Nam",
            read,
            result="Thứ tư, 05/08/2026, 09:00",
            counts_as_capability=False,
        ),
        spec(
            "web_search",
            "Tìm kiếm web",
            "Tìm thông tin mới trên web theo chuỗi nguồn, DuckDuckGo luôn đứng cuối",
            read,
            has_settings=True,
        ),
        spec(
            "web_fetch",
            "Đọc trang web",
            "Đọc nội dung 1 URL công khai (đã chặn IP nội bộ chống SSRF)",
            read,
            has_settings=True,
        ),
        spec(
            "read_image",
            "Nhìn kỹ ảnh",
            "Hỏi model đọc ảnh (sidecar) một câu cụ thể về ảnh đã nhận - đếm, đọc chữ nhỏ, soi chi tiết",
            read,
            has_settings=True,
            available=lambda _scope: registry.sidecar_configured,
            unavailable_hint="Bấm Settings để cấu hình model sidecar đọc ảnh",
            runs_in_scheduled_turn=False,
        ),
        spec(
            "get_group_info",
            "Thông tin nhóm",
            "Xem tên nhóm, số thành viên, danh sách thành viên của nhóm hiện tại",
            read,
            result=_failure("Đây là chat riêng, không có thông tin nhóm."),
        ),
        spec(
            "kb_search",
            "Tra kho tri thức",
            "Tra tài liệu do chủ bot nạp lên (chính sách, bảng giá, hướng dẫn)",
            read,
            available=lambda scope: (
                bool(registry.kb_agent_ids)
                if scope.agent_id == ""
                else scope.agent_id in registry.kb_agent_ids
            ),
            unavailable_hint="Kho tri thức chưa có nguồn nào, hoặc agent này chưa được gán nguồn",
        ),
        spec(
            "add_reaction",
            "Thả cảm xúc",
            "Thả reaction (tim, like...) vào tin nhắn trong hội thoại",
            action,
            counts_as_capability=False,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "send_file",
            "Gửi file",
            "Gửi file từ kho shared-files hoặc tải từ URL công khai rồi gửi",
            action,
            result=lambda args: _failure(
                f"Không tìm thấy file {args.get('source', '')} trong kho shared-files."
            ),
            runs_in_scheduled_turn=False,
        ),
        spec(
            "create_word_document",
            "Tạo file Word",
            "Soạn nội dung thành file .docx (tiêu đề, đoạn văn, gạch đầu dòng, bảng) rồi gửi luôn",
            action,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "create_excel_file",
            "Tạo file Excel",
            "Soạn bảng số liệu thành file .xlsx có công thức tính sẵn rồi gửi luôn",
            action,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "create_image",
            "Vẽ ảnh AI",
            "Vẽ ảnh mới hoặc sửa ảnh người dùng vừa gửi (đổi màu, xóa vật thể, đổi phong cách) rồi gửi luôn",
            action,
            has_settings=True,
            available=lambda _scope: registry.image_gen_configured,
            unavailable_hint="Bấm Settings để cấu hình endpoint + model vẽ ảnh",
            runs_in_scheduled_turn=False,
        ),
        spec(
            "tai_video",
            "Tải video TikTok/Facebook",
            "Người dùng dán link TikTok hoặc Facebook, bot tải bản không watermark rồi gửi lại",
            action,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "tag_member",
            "Tag thành viên",
            "Nhắc tên (@mention) thành viên trong nhóm khi trả lời",
            action,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "save_memory",
            "Ghi nhớ lâu dài",
            "Tự lưu fact về người dùng/nhóm để nhớ qua các phiên chat sau",
            action,
            runs_in_scheduled_turn=False,
        ),
        spec(
            "schedule_task",
            "Lịch hẹn",
            "Đặt/xem/sửa/hủy lịch để bot tự nhắn lại đúng cuộc trò chuyện này ở một mốc giờ trong tương lai",
            action,
            available=lambda _scope: bool(get_tuning("SCHEDULER_ENABLED")),
            unavailable_hint='Bật "Bật lịch hẹn" trong Cấu hình > Lịch hẹn để dùng tool này',
            runs_in_scheduled_turn=False,
        ),
    ]


@dataclass
class FakeToolRegistry:
    """``ToolRegistry`` over the zalo-agent catalogue. ``extra`` adds specs (an MCP tool, a clinic tool)."""

    sidecar_configured: bool = False
    image_gen_configured: bool = False
    kb_agent_ids: frozenset[str] = frozenset()
    extra: Sequence[ToolSpec] = ()
    default_caps: ChannelCapabilities = field(default_factory=make_caps)
    built: dict[str, list[FakeTool]] = field(default_factory=dict[str, list[FakeTool]])
    """Every tool object built so far, by key (tests read ``built["send_file"][0].calls``)."""

    def definitions(self) -> Sequence[ToolSpec]:
        return [*_builtin_catalogue(self), *self.extra]

    def check_availability(self, spec: ToolSpec, scope: ToolScope) -> ToolAvailability:
        hint = scope.channel.blocked_tools.get(spec.key)
        if hint is not None:
            return ToolAvailability(usable=False, hint=hint)
        if spec.available is not None and not spec.available(scope):
            return ToolAvailability(usable=False, hint=spec.unavailable_hint)
        return ToolAvailability(usable=True)

    def list_available(self, scope: ToolScope, *, isolated: bool = False) -> Sequence[ToolSpec]:
        disabled = {*scope.agent_disabled_tools, *scope.account_disabled_tools}
        out: list[ToolSpec] = []
        for spec in self.definitions():
            if spec.key in disabled:
                continue
            if isolated and not spec.runs_in_scheduled_turn:
                continue
            if self.check_availability(spec, scope).usable:
                out.append(spec)
        return out

    async def build_agent_tools(self, ctx: ToolContext) -> Mapping[str, AgentTool]:
        caps = ctx.channel.capabilities() if ctx.channel is not None else self.default_caps
        scope = ToolScope(
            agent_id=ctx.agent.id,
            agent_disabled_tools=ctx.agent.disabled_tools,
            account_disabled_tools=ctx.account.disabled_tools,
            channel=caps,
        )
        return {spec.key: spec.build(ctx) for spec in self.list_available(scope, isolated=ctx.isolated)}
