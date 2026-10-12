"""The knowledge store as the agent and the admin pages use it: its settings, the tools ``kb_search`` and
``kb_read``, the prompt section that tells the agent how to look things up, and the gaps it records."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from agent_app.plugins import PluginContext, PluginDatabase, PluginError
from agentcore import PromptEnv, SessionSection, ToolContext, ToolOutput, ToolSpec
from agentcore.prompt.data import SessionData

from .embedder import IDLE_S, Embedder
from .embedding import EmbeddingClient, EmbeddingConfig
from .ingest import Ingest, new_id
from .models import Gap, as_mapping
from .search import Searcher, VectorPlan, tool_detail, tool_text
from .store import InMemoryKnowledgeStore, KnowledgeStore, PostgresKnowledgeStore
from .text import fold

logger = logging.getLogger(__name__)

SETTINGS_KEY: Final = "settings"
KEY_RECORD: Final = "embedding_api_key"
"""The embedding service's key, sealed with the service's key; never inside the settings JSON."""
DERIVED: Final = frozenset({"api_key", "has_key", "chunks_without_vector", "origin"})
"""Embedding fields a patch cannot store as settings (the key has its own record; the rest are worked out)."""
READ_CHARS: Final = 8000
# the chunks handed to the agent; kept under the tool's result limit so none is cut mid-text
MAX_CHAR_BUDGET: Final = 8000
GAP_MIN_CHARS: Final = 6

GUIDANCE: Final = """## Kho tri thức
Phòng khám có một kho tài liệu (dịch vụ, bảng giá, gói, khuyến mại, chính sách đặt/đổi/hủy lịch, thanh toán,
chăm sóc sau điều trị, câu hỏi thường gặp). Cách làm:
- Câu hỏi về phòng khám, dịch vụ, giá, chính sách hay quy trình: gọi `kb_search` trước khi trả lời. Câu hỏi có
  nhiều ý thì tìm từng ý; không thấy thì tìm lại với từ khác (tên dịch vụ, tên chính sách).
- Chỉ trả lời bằng những gì các đoạn tìm được nói. Con số (giá, số buổi, số ngày, phần trăm) phải lấy đúng như
  trong đoạn; tự tính (ví dụ giảm 10%) thì nói rõ là tính từ giá nào.
- Cần đọc trọn một tài liệu (bảng, điều kiện dài) thì gọi `kb_read` với mã ở đầu đoạn.
- Không tìm thấy: nói thật là chưa có thông tin đó và đề nghị nhân viên liên hệ lại, không đoán.
- Không nhắc tên công cụ hay mã tài liệu với khách; trả lời ngắn, tự nhiên, bằng tiếng Việt."""


def default_settings(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "embedding": {
            "base_url": str(config.get("embedding_base_url", "")),
            "model": str(config.get("embedding_model", "qwen/qwen3-embedding-8b")),
            "dimensions": int(config.get("embedding_dimensions", 1024)),
            "query_prefix": str(config.get("embedding_query_prefix", "")),
            "document_prefix": str(config.get("embedding_document_prefix", "")),
            "has_key": False,
            "origin": "profile",
            "chunks_without_vector": 0,
        },
        "parser": {"kind": "simple", "docling_url": "", "origin": "profile"},
        "labelling": {"enabled": False, "model_entry": None, "rerank": False},
        "search": {
            "results": int(config.get("results", 6)),
            "min_score": float(config.get("vector_min_similarity", 0.35)),
            "char_budget": min(int(config.get("char_budget", 6000)), MAX_CHAR_BUDGET),
            "patient_channel_prefix": "",
            "patient_only_approved": False,
        },
        "benchmark_mode": bool(config.get("benchmark_mode", False)),
    }


class SearchArgs(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=300,
        description="Điều cần tìm, bằng lời của khách hoặc từ khóa: tên dịch vụ, giá, chính sách...",
    )
    results: int | None = Field(
        default=None, ge=1, le=10, description="Số đoạn muốn lấy (mặc định theo cài đặt)."
    )


class ReadArgs(BaseModel):
    doc_code: str = Field(
        min_length=1,
        max_length=120,
        description="Mã ở đầu một đoạn kb_search trả về (mã tài liệu hoặc mã nguồn).",
    )


class KnowledgePlugin:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        store: KnowledgeStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        client: EmbeddingClient | None = None,
    ) -> None:
        self._ctx = ctx
        self._clock = clock
        database = ctx.database
        self._database: PluginDatabase | None = database
        self.store: KnowledgeStore = store or (
            InMemoryKnowledgeStore()
            if database is None
            else PostgresKnowledgeStore(database.engine, tenant_id=database.tenant_id, agent=database.agent)
        )
        self._zone = _zone(str(ctx.config.get("timezone", "Asia/Ho_Chi_Minh")))
        self._vector_timeout = float(ctx.config.get("vector_timeout_s", 6.0))
        self.client = client or EmbeddingClient()
        self.embedder = Embedder(
            self.store,
            self.client,
            self.embedding_config,
            logger=ctx.logger,
            clock=clock,
            idle_s=float(ctx.config.get("embedding_idle_s", IDLE_S)),
        )
        self.ingest = Ingest(
            self.store,
            clock=clock,
            today=lambda: clock().astimezone(self._zone).date(),
            on_change=self.embedder.wake,
        )
        self.searcher = Searcher(self.store)
        self._ready = database is None

    def register(self) -> None:
        ctx = self._ctx
        ctx.register_tool(
            ToolSpec(
                name="kb_search",
                description=(
                    "Tìm trong kho tài liệu của phòng khám (dịch vụ, giá, gói, khuyến mại, chính sách, chăm "
                    "sóc, "
                    "câu hỏi thường gặp). Trả về các đoạn liên quan kèm mã tài liệu."
                ),
                args_model=SearchArgs,
                handler=self._search_tool,
                timeout_s=15.0,
                max_result_chars=9000,
                read_only=True,
            )
        )
        ctx.register_tool(
            ToolSpec(
                name="kb_read",
                description=(
                    "Đọc trọn một tài liệu của kho theo mã tài liệu (khi cần cả bảng hay điều kiện dài)."
                ),
                args_model=ReadArgs,
                handler=self._read_tool,
                timeout_s=10.0,
                max_result_chars=READ_CHARS + 200,
                read_only=True,
            )
        )
        ctx.register_prompt_section(SessionSection("knowledge", _guidance))
        ctx.register_job("embed", self.embedder.run)

    async def ready(self) -> None:
        """Raises ``PluginError`` (what to run) while the plugin's tables are missing; checked once."""
        if self._ready or self._database is None:
            return
        await self._database.require_migrations()
        self._ready = True

    async def settings(self) -> dict[str, Any]:
        saved = await self._ctx.storage.get(SETTINGS_KEY)
        base = default_settings(self._ctx.config)
        stored = as_mapping(saved)
        merged = {key: _merged(base[key], stored.get(key)) for key in base}
        merged["embedding"]["has_key"] = await self._ctx.storage.get(KEY_RECORD) is not None
        return merged

    async def embedding_config(self) -> EmbeddingConfig:
        """The embedding settings and the key, ready for the client; ``key_broken`` when a stored key no
        longer decrypts (the service's secret key changed)."""
        values = (await self.settings())["embedding"]
        sealed = await self._ctx.storage.get(KEY_RECORD)
        key, broken = "", False
        if isinstance(sealed, str):
            try:
                key = self._ctx.decrypt(sealed)
            except PluginError:
                broken = True
        return EmbeddingConfig(
            base_url=str(values["base_url"]),
            model=str(values["model"]),
            dimensions=int(values["dimensions"]),
            query_prefix=str(values["query_prefix"]),
            document_prefix=str(values["document_prefix"]),
            api_key=key,
            key_broken=broken,
        )

    async def vector_plan(self, search: Mapping[str, Any]) -> VectorPlan | None:
        """How a search uses vectors; None while the embedding service is not connected (keyword only)."""
        if not (await self.embedding_config()).ready:
            return None
        return VectorPlan(float(search["min_score"]), self._vector_timeout, self.embedder.query_vector)

    async def save_settings(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        current = await self.settings()
        resets = [group for group in patch.get("reset", []) if group in ("embedding", "parser")]
        base = default_settings(self._ctx.config)
        changed = copy.deepcopy(current)
        for group, given in patch.items():
            values = as_mapping(given)
            if group not in changed or group in ("reset", "benchmark_mode") or not values:
                continue
            changed[group] = {**changed[group], **{k: v for k, v in values.items() if k not in DERIVED}}
            if group in ("embedding", "parser"):
                changed[group]["origin"] = "saved"
            if group == "embedding" and "api_key" in values:
                await self._store_key(str(values["api_key"]).strip())
        if "benchmark_mode" in patch:
            changed["benchmark_mode"] = bool(patch["benchmark_mode"])
        for group in resets:
            changed[group] = base[group]
        stored = {**changed, "embedding": {k: v for k, v in changed["embedding"].items() if k != "has_key"}}
        await self._ctx.storage.put(SETTINGS_KEY, stored)
        self.embedder.wake()
        return {**changed, "embedding": {**changed["embedding"], "has_key": await self._has_key()}}

    async def _has_key(self) -> bool:
        return await self._ctx.storage.get(KEY_RECORD) is not None

    async def _store_key(self, key: str) -> None:
        """Seals the key into its own record; an empty one removes it. Raises ``PluginError`` when the service
        has no secret key to seal with."""
        if key:
            await self._ctx.storage.put(KEY_RECORD, self._ctx.encrypt(key))
        else:
            await self._ctx.storage.delete(KEY_RECORD)

    def asked_on(self, ctx: ToolContext) -> date:
        """The day the question is asked, in the clinic's time zone (the turn's time when there is one)."""
        moment = ctx.now or self._clock()
        return moment.astimezone(self._zone).date()

    async def record_gap(self, question: str, channel: str) -> None:
        folded = " ".join(fold(question).split())
        if len(folded) < GAP_MIN_CHARS:
            return
        await self.store.record_gap(
            Gap(new_id("gap"), folded, question.strip()[:500], 1, channel, self._clock())
        )

    async def _search_tool(self, args: SearchArgs, ctx: ToolContext) -> ToolOutput:
        try:
            await self.ready()
        except PluginError as err:
            return ToolOutput(text=f"Kho tri thức chưa sẵn sàng: {err}", is_error=True)
        settings = (await self.settings())["search"]
        result = await self.searcher.search(
            args.query,
            self.asked_on(ctx),
            results=args.results or int(settings["results"]),
            char_budget=min(int(settings["char_budget"]), MAX_CHAR_BUDGET),
            services=await self.store.services(),
            vector=await self.vector_plan(settings),
        )
        if not result.final:
            await self.record_gap(args.query, ctx.channel or "")
        return ToolOutput(text=tool_text(result), detail=tool_detail(result))

    async def _read_tool(self, args: ReadArgs, ctx: ToolContext) -> ToolOutput:
        try:
            await self.ready()
        except PluginError as err:
            return ToolOutput(text=f"Kho tri thức chưa sẵn sàng: {err}", is_error=True)
        source = await self.store.in_force(args.doc_code.strip(), self.asked_on(ctx))
        if source is None:
            return ToolOutput(
                text=f"Không có tài liệu mã {args.doc_code} đang có hiệu lực trong kho.", is_error=True
            )
        body = source.markdown[:READ_CHARS]
        more = (
            "\n\n…(còn tiếp; tìm bằng kb_search để lấy phần cần)" if len(source.markdown) > READ_CHARS else ""
        )
        return ToolOutput(
            text=f"{source.doc_code or source.id} · {source.title}\n\n{body}{more}",
            detail={"doc_ids": [source.doc_code or source.id], "source_id": source.id, "chars": len(body)},
        )


def _guidance(env: PromptEnv, _data: SessionData) -> str | None:
    return GUIDANCE if "kb_search" in env.tool_names else None


def _merged(base: Any, saved: Any) -> Any:
    known = as_mapping(base)
    given = as_mapping(saved)
    if known:
        return {**known, **{k: v for k, v in given.items() if k in known}}
    return base if saved is None else saved


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("unknown time zone %s; using UTC", name)
        return ZoneInfo("UTC")
