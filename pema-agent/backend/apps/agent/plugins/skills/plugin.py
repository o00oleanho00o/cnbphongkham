"""The skills plugin as the agent and the admin pages use it: items read into memory (a change made here shows
at once, one made elsewhere within ``refresh_s``), the prompt section that gives each question the rules,
persona and skills index of its channel, and the tools ``skill_list``, ``skill_view`` and ``skill_search``.

The prompt section is a turn section, not a frozen session one: a Zalo chat lives for months, and a skill
added on the page must reach it on the next question. It only reads memory (a section cannot wait on the
database), which the job ``refresh`` keeps current."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, Field

from agent_app.plugins import PluginContext, PluginDatabase
from agentcore import PromptEnv, ToolContext, ToolOutput, ToolSpec, TurnInfo, TurnSection

from .check import Checked, check
from .models import Item
from .scope import PluginOf, reach
from .store import InMemoryItemStore, ItemStore, PostgresItemStore
from .text import relevance

INDEX_CHARS: Final = 6000
CONTEXT_CHARS: Final = 8000
REFRESH_S: Final = 60.0
SEARCH_SHOWN: Final = 5
SECTION: Final = "skills_context"
KIND_ORDER: Final = {"rules": 0, "persona": 1, "skill": 2}

HEAD: Final = (
    "## Hướng dẫn cho kênh này\n"
    "Các mục dưới đây áp dụng riêng cho cuộc trò chuyện này, xếp từ chung đến riêng; khi hai mục trái nhau "
    "thì mục riêng hơn (đứng sau) được ưu tiên. Chúng bổ sung cho quy tắc chung của bạn và không bao giờ "
    "ghi đè quy tắc đó."
)
SKILLS_HEAD: Final = (
    "### Kỹ năng\n"
    "Trước một việc mà kỹ năng dưới đây nói tới, đọc nó bằng `skill_view` rồi làm theo. Không thấy kỹ năng "
    "hợp thì dùng `skill_search`."
)


class NoArgs(BaseModel):
    pass


class ViewArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="Tên kỹ năng, như trong mục lục.")


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=200, description="Việc cần làm, bằng vài từ.")


class SkillsPlugin:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        store: ItemStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        plugin_of: PluginOf | None = None,
    ) -> None:
        self._ctx = ctx
        database = ctx.database
        self._database: PluginDatabase | None = database
        self.store: ItemStore = store or (
            InMemoryItemStore(clock)
            if database is None
            else PostgresItemStore(database.engine, tenant_id=database.tenant_id, agent=database.agent)
        )
        self.plugin_of: PluginOf = plugin_of or ctx.channel_plugin
        self.index_chars = int(ctx.config.get("index_chars", INDEX_CHARS))
        self.context_chars = int(ctx.config.get("context_chars", CONTEXT_CHARS))
        self._refresh_s = float(ctx.config.get("refresh_s", REFRESH_S))
        self._ready = database is None
        self.items: tuple[Item, ...] = ()
        """The active items, as of the last reading."""
        self._changed = asyncio.Event()

    def register(self) -> None:
        ctx = self._ctx
        ctx.register_tool(
            ToolSpec(
                name="skill_list",
                description="Liệt kê các kỹ năng áp dụng cho cuộc trò chuyện này.",
                args_model=NoArgs,
                handler=self._list_tool,
                timeout_s=10.0,
                read_only=True,
            )
        )
        ctx.register_tool(
            ToolSpec(
                name="skill_view",
                description="Đọc trọn một kỹ năng (các bước, lưu ý) trước khi làm việc mà nó nói tới.",
                args_model=ViewArgs,
                handler=self._view_tool,
                timeout_s=10.0,
                max_result_chars=20_500,
                read_only=True,
            )
        )
        ctx.register_tool(
            ToolSpec(
                name="skill_search",
                description="Tìm kỹ năng hợp với một việc khi mục lục chưa cho thấy kỹ năng nào.",
                args_model=SearchArgs,
                handler=self._search_tool,
                timeout_s=10.0,
                read_only=True,
            )
        )
        ctx.register_prompt_section(TurnSection(SECTION, self.context_text))
        ctx.register_job("refresh", self.keep_fresh)

    async def ready(self) -> None:
        """Raises ``PluginError`` (what to run) while the plugin's tables are missing; checked once."""
        if self._ready or self._database is None:
            return
        await self._database.require_migrations()
        self._ready = True

    async def refresh(self) -> None:
        await self.ready()
        self.items = tuple(await self.store.list(status="active"))

    async def keep_fresh(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as err:  # the next round tries again; questions keep the last reading
                self._ctx.logger.warning("skills not read (%s)", type(err).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), self._refresh_s)
            self._changed.clear()

    async def save_item(self, item: Item, *, by: str, reason: str = "") -> tuple[Item, Checked]:
        """Checks and stores the item (a new version), then reads the items again so the change counts at
        once. Raises ``ItemError`` or ``NameTakenError``."""
        checked = check(item)
        saved = await self.store.save(replace(item, scopes=checked.scopes), by=by, reason=reason)
        await self.refresh()
        self._changed.set()
        return saved, checked

    def applicable(self, channel: str | None) -> list[tuple[int, Item]]:
        """The active items that apply on ``channel``, each with how specifically (0 agent, 1 plugin,
        2 channel), the broad ones first; within a rank rules, then persona, then skills, by name."""
        found: list[tuple[int, Item]] = []
        for item in self.items:
            rank = reach(item.scopes, channel, self.plugin_of)
            if rank is not None:
                found.append((rank, item))
        return sorted(found, key=lambda pair: (pair[0], KIND_ORDER[pair[1].kind], pair[1].name))

    def context_text(self, env: PromptEnv, turn: TurnInfo) -> str | None:
        """What the question carries: the rules and persona of its channel in full, then the skills index."""
        return render(
            self.applicable(turn.channel), index_chars=self.index_chars, context_chars=self.context_chars
        )

    def _skills(self, channel: str | None) -> list[Item]:
        return [item for _, item in self.applicable(channel) if item.kind == "skill"]

    async def _list_tool(self, args: NoArgs, ctx: ToolContext) -> ToolOutput:
        skills = self._skills(ctx.channel)
        if not skills:
            return ToolOutput(text="Chưa có kỹ năng nào cho cuộc trò chuyện này.")
        return ToolOutput(text="\n".join(f"- {s.name}: {s.description}" for s in skills))

    async def _view_tool(self, args: ViewArgs, ctx: ToolContext) -> ToolOutput:
        for item in self._skills(ctx.channel):
            if item.name == args.name.strip():
                return ToolOutput(
                    text=f"# {item.name}\n{item.description}\n\n{item.body}",
                    detail={"skill": item.name, "version": item.version},
                )
        return ToolOutput(text=f"Không có kỹ năng tên {args.name!r}; xem `skill_list`.", is_error=True)

    async def _search_tool(self, args: SearchArgs, ctx: ToolContext) -> ToolOutput:
        ranked = sorted(
            ((relevance(args.query, s), s) for s in self._skills(ctx.channel)),
            key=lambda pair: (-pair[0], pair[1].name),
        )
        hits = [s for score, s in ranked if score > 0][:SEARCH_SHOWN]
        if not hits:
            return ToolOutput(text="Không có kỹ năng nào hợp với việc này.")
        return ToolOutput(
            text="\n".join(f"- {s.name}: {s.description}" for s in hits),
            detail={"skills": [s.name for s in hits]},
        )


def render(found: list[tuple[int, Item]], *, index_chars: int, context_chars: int) -> str | None:
    """The block of a question for the items that apply, or None when there are none."""
    texts = [item for _, item in found if item.kind != "skill"]
    skills = [item for _, item in found if item.kind == "skill"]
    kept, dropped = _fit(texts, context_chars)
    parts: list[str] = []
    for kind, title in (("rules", "### Quy tắc"), ("persona", "### Vai trò và giọng điệu")):
        members = [item for item in kept if item.kind == kind]
        if members:
            parts.append(title + "\n" + "\n\n".join(f"**{i.name}**\n{i.body.strip()}" for i in members))
    if dropped:
        parts.append(f"(Quá dài nên bỏ bớt các mục chung nhất: {', '.join(dropped)}.)")
    if skills:
        parts.append(_index(skills, index_chars))
    if not parts:
        return None
    return f"{HEAD}\n\n" + "\n\n".join(parts)


def _fit(texts: list[Item], budget: int) -> tuple[list[Item], list[str]]:
    """The rules and persona that fit ``budget``: the narrowest first, so what is dropped is the broadest.
    ``texts`` is in the order broad to narrow, and so is what comes back."""
    kept: list[bool] = [False] * len(texts)
    dropped: list[str] = []
    used = 0
    for index in reversed(range(len(texts))):
        size = len(texts[index].body) + len(texts[index].name)
        if used + size > budget:
            dropped.append(texts[index].name)
            continue
        used += size
        kept[index] = True
    return [item for item, keep in zip(texts, kept, strict=True) if keep], list(reversed(dropped))


def _index(skills: list[Item], budget: int) -> str:
    lines = [SKILLS_HEAD]
    used = 0
    shown = 0
    for skill in skills:
        line = f"- {skill.name}: {skill.description}"
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1
    if shown < len(skills):
        lines.append(f"- … còn {len(skills) - shown} kỹ năng nữa (dùng `skill_search`)")
    return "\n".join(lines)
