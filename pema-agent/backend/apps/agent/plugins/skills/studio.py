"""The chat that helps staff write skills: a conversation with the agent's own model that has three tools
of its own (read the items, read one, save one) and nothing else. It is not the agent customers talk to and
it shares none of its tools, so a customer can never reach it.

What it saves goes through the same check as an item written any other way. A new item is a draft until
staff press "Dùng" on the page; a change to an item already in use takes effect at once and the page offers
to undo it (every save is a version). Conversations live in this process's memory: a restart starts them
over."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Final

from pydantic import BaseModel, Field

from agentcore import (
    InMemorySessionStore,
    LoopPolicy,
    ModelClient,
    PromptBuilder,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolSpec,
    run_turn,
)
from agentcore.channels import valid_channel_name

from .check import ItemError
from .models import Item, Kind, Status, new_id
from .plugin import SkillsPlugin
from .scope import scopes_text
from .store import NameTakenError

CHANNEL: Final = "skills-studio"
POLICY: Final = LoopPolicy(max_steps=8, max_output_tokens=4096, max_turn_s=180.0, reasoning="low")
MAX_KNOWN: Final = 50

SYSTEM: Final = """Bạn là trợ lý soạn "kỹ năng" cho agent chăm sóc khách của một phòng khám.
Người nói chuyện với bạn là nhân viên phòng khám, không phải khách.

Việc của bạn: nghe nhân viên mô tả một cách làm việc, hỏi lại ngắn gọn nếu còn thiếu điều quan trọng,
rồi soạn bản nháp bằng công cụ `studio_save`. Có ba loại:
- skill: các bước làm một việc; agent đọc khi cần.
- rules: quy tắc luôn đi kèm mỗi câu hỏi của kênh; phải ngắn.
- persona: vai trò, cách xưng hô, giọng điệu.

Nơi áp dụng (scopes): "agent" là cả agent (mặc định khi để trống), "plugin:<tên>" là mọi tài khoản của
một plugin, "channel:<tên>" là đúng một tài khoản. {known}

Nguyên tắc:
- Một kỹ năng chỉ chứa cách làm: các bước, câu nên hỏi lại, khi nào chuyển nhân viên, giọng điệu.
  Không ghi giá, chính sách hay số liệu vì chúng nằm ở kho tri thức và đổi theo thời gian.
- Không ghi thông tin cá nhân của khách (tên, số điện thoại, CCCD).
- Viết ngắn, rõ, câu mệnh lệnh. Mô tả một dòng nói khi nào nên dùng.
- Tên gồm chữ thường, số và dấu gạch ngang, ví dụ tiep-nhan-dat-lich.
- Muốn sửa một mục đã có thì đọc nó trước bằng `studio_view`, rồi lưu lại bản đầy đủ đã sửa.
- Mục mới là bản nháp: nhân viên đọc rồi bấm "Dùng" thì agent mới dùng. Sửa mục đang dùng thì có hiệu
  lực ngay và nhân viên có thể hoàn tác. Nói rõ điều này sau khi lưu.
- Bạn chỉ soạn và sửa nội dung; không làm việc nào khác.
Trả lời ngắn gọn bằng tiếng Việt."""


class NoArgs(BaseModel):
    pass


class ViewArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: Kind | None = Field(default=None, description="Chỉ cần khi hai mục khác loại trùng tên.")


class SaveArgs(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=300, description="Một dòng: khi nào dùng.")
    body: str = Field(min_length=1, max_length=20_000, description="Nội dung Markdown đầy đủ.")
    scopes: list[str] | None = Field(
        default=None, max_length=20, description="Bỏ trống để giữ nguyên (mục mới: cả agent)."
    )
    status: Status | None = Field(default=None, description="Bỏ trống: mục mới là nháp, mục cũ giữ nguyên.")


class Known(BaseModel):
    """What the page knows of the agent, so the model can suggest real places to apply an item."""

    channels: list[str] = Field(default_factory=list[str], max_length=MAX_KNOWN)
    plugins: list[str] = Field(default_factory=list[str], max_length=MAX_KNOWN)


@dataclass(frozen=True, slots=True)
class Touched:
    item: Item
    before_version: int | None
    """The version the item had before this conversation turn changed it; None when the turn made it."""


@dataclass(frozen=True, slots=True)
class StudioReply:
    text: str
    touched: list[Touched]
    stop: str


def system_text(known: Known) -> str:
    channels = [name for name in known.channels if valid_channel_name(name)]
    plugins = [name for name in known.plugins if valid_channel_name(name)]
    lines: list[str] = []
    if channels:
        lines.append(f"Các kênh hiện có: {', '.join(channels)}.")
    if plugins:
        lines.append(f"Các plugin đang bật: {', '.join(plugins)}.")
    return SYSTEM.format(known=" ".join(lines))


class Studio:
    def __init__(self, plugin: SkillsPlugin, model: Callable[[], ModelClient]) -> None:
        self._plugin = plugin
        self._model = model
        self._store = InMemorySessionStore()
        self._locks: dict[str, asyncio.Lock] = {}

    async def chat(self, conversation_id: str, text: str, known: Known, *, by: str) -> StudioReply:
        """One turn of the conversation. Raises ``ModelError`` when the model cannot be reached."""
        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            touched: dict[str, Touched] = {}
            result = await run_turn(
                session_id=f"{CHANNEL}:{conversation_id}",
                user_text=text,
                prompt=PromptBuilder.fixed(system_text(known)),
                model=self._model(),
                tools=ToolRegistry(self._tools(by, touched)),
                store=self._store,
                policy=POLICY,
                channel=CHANNEL,
            )
            return StudioReply(result.text, list(touched.values()), result.stop)

    def _tools(self, by: str, touched: dict[str, Touched]) -> list[ToolSpec[Any]]:
        plugin = self._plugin

        async def list_items(args: NoArgs, ctx: ToolContext) -> ToolOutput:
            items = await plugin.store.list()
            if not items:
                return ToolOutput(text="Chưa có mục nào.")
            return ToolOutput(
                text="\n".join(
                    f"- [{i.kind}, {i.status}] {i.name}: {i.description} (áp dụng: {scopes_text(i.scopes)})"
                    for i in items
                )
            )

        async def view(args: ViewArgs, ctx: ToolContext) -> ToolOutput:
            found = [
                i
                for i in await plugin.store.list()
                if i.name == args.name.strip() and (args.kind is None or i.kind == args.kind)
            ]
            if not found:
                return ToolOutput(text=f"Không có mục tên {args.name!r}; xem `studio_list`.", is_error=True)
            if len(found) > 1:
                return ToolOutput(text="Có nhiều mục trùng tên khác loại; cho biết `kind`.", is_error=True)
            item = found[0]
            head = (
                f"[{item.kind}, {item.status}, phiên bản {item.version}] áp dụng: {scopes_text(item.scopes)}"
            )
            return ToolOutput(text=f"{head}\n{item.description}\n\n{item.body}")

        async def save(args: SaveArgs, ctx: ToolContext) -> ToolOutput:
            name = args.name.strip()
            existing = next(
                (i for i in await plugin.store.list() if i.kind == args.kind and i.name == name), None
            )
            if existing is None:
                item = Item(
                    id=new_id(),
                    kind=args.kind,
                    name=name,
                    description=args.description.strip(),
                    body=args.body,
                    status=args.status or "draft",
                    origin="agent",
                    scopes=args.scopes or [],
                )
            else:
                item = replace(
                    existing,
                    description=args.description.strip(),
                    body=args.body,
                    status=args.status or existing.status,
                    scopes=existing.scopes if args.scopes is None else args.scopes,
                )
            try:
                saved, checked = await plugin.save_item(item, by=by, reason="soạn bằng chat")
            except (ItemError, NameTakenError) as err:
                return ToolOutput(text=str(err), is_error=True)
            first = touched.get(saved.id)
            before = first.before_version if first else (existing.version if existing else None)
            touched[saved.id] = Touched(saved, before)
            note = " ".join(checked.warnings)
            state = "bản nháp, chờ nhân viên bấm Dùng" if saved.status == "draft" else saved.status
            return ToolOutput(
                text=f"Đã lưu {saved.kind} {saved.name!r} (phiên bản {saved.version}): {state}. {note}"
            )

        return [
            ToolSpec(
                name="studio_list",
                description="Liệt kê các kỹ năng, quy tắc và giọng điệu đã có.",
                args_model=NoArgs,
                handler=list_items,
                timeout_s=15.0,
                read_only=True,
            ),
            ToolSpec(
                name="studio_view",
                description="Đọc trọn một mục đã có theo tên, trước khi sửa nó.",
                args_model=ViewArgs,
                handler=view,
                timeout_s=15.0,
                max_result_chars=20_500,
                read_only=True,
            ),
            ToolSpec(
                name="studio_save",
                description=(
                    "Lưu một kỹ năng, quy tắc hoặc giọng điệu: mục mới thành bản nháp, mục cùng loại và "
                    "tên đã có thì ghi bản mới đầy đủ."
                ),
                args_model=SaveArgs,
                handler=save,
                timeout_s=15.0,
            ),
        ]
