"""Scenarios: episodes cut from the kept conversations, and the agent's use of them.

Three pieces of work run here. ``cut_once`` turns conversations that have gone quiet into episodes (what a
customer asked, how the staff reacted). ``embed_once`` gives each episode a vector through the embedding
service another plugin provides (``knowledge``) and joins episodes that ask the same thing in other words.
``search`` finds the episodes closest to a question, by meaning while the service answers and by words when
it does not.

The agent meets them in two ways. A ``pre_model`` hook looks at the customer's latest question and, when
scenarios are close enough, adds them to that question as "how the staff reacted before"; the tool
``scenario_search`` lets the agent look for more. Scenarios teach the shape of an answer, never its numbers:
prices and rules come from the knowledge store, because an old answer may be out of date."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from pydantic import BaseModel, Field

from agent_app.plugins import EmbeddingService, EmbeddingUnavailableError
from agentcore import ToolContext, ToolOutput, ToolSpec
from agentcore.harness.hooks import HookContext, PreModelHook
from agentcore.harness.model.types import LlmRequest
from agentcore.messages import Message, TextBlock

from .episode_store import EpisodeStore
from .episodes import GAP_S, cut
from .scenario_models import Counts, Hit, Reach
from .settings import ScenarioSettings, Settings
from .store import ConversationStore
from .words import query_terms

CUT_EVERY_S: Final = 120.0
EMBED_IDLE_S: Final = 10.0
EMBED_BATCH: Final = 16
EMBED_TIMEOUT_S: Final = 60.0
QUERY_TIMEOUT_S: Final = 2.5
CUT_CONVERSATIONS: Final = 20
CUT_MESSAGES: Final = 5000
MERGE_SIMILARITY: Final = 0.93
"""Two questions this alike (by meaning) are one scenario that was asked twice."""
MIN_QUESTION_CHARS: Final = 6
SHOWN_CHARS: Final = 3200
LINE_CHARS: Final = 600
REPEAT_BONUS: Final = 0.02
CACHE: Final = 128
BACKOFF_S: Final = (10.0, 30.0, 120.0, 300.0)

HEAD: Final = (
    "## Kịch bản mẫu: cách nhân viên đã phản ứng\n"
    "Đây là vài cuộc trò chuyện thật trước đây, đã che thông tin cá nhân, khi khách hỏi điều gần giống. Học "
    "bước đi, giọng điệu, điều nhân viên hỏi lại và lúc nào họ chuyển cho người. KHÔNG chép số liệu (giá, "
    "chính sách, thời gian, số buổi): câu trả lời cũ có thể đã lỗi thời, số liệu chỉ lấy từ kho tri thức "
    "(`kb_search`). Không nhắc tới các cuộc trò chuyện này với khách."
)

logger = logging.getLogger(__name__)


class SearchArgs(BaseModel):
    query: str = Field(
        min_length=3,
        max_length=300,
        description="Điều khách hỏi hoặc tình huống cần xử lý, bằng lời của khách.",
    )


@dataclass(frozen=True, slots=True)
class CutResult:
    conversations: int
    episodes: int
    joined: int


class Scenarios:
    def __init__(
        self,
        *,
        conversations: ConversationStore,
        episodes: EpisodeStore,
        settings: Callable[[], Awaitable[Settings]],
        embeddings: Callable[[], EmbeddingService | None],
        plugin_of: Callable[[str], str | None],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        logger: logging.Logger = logger,
    ) -> None:
        self._conversations = conversations
        self.episodes = episodes
        self._settings = settings
        self._embeddings = embeddings
        self._plugin_of = plugin_of
        self._clock = clock
        self._logger = logger
        self.embedding_error: str | None = None
        """What the embedding service last said when it could not be used; None while it works."""
        self._cache: OrderedDict[tuple[str, str], str | None] = OrderedDict()
        self._wake = asyncio.Event()

    # --- making scenarios ---

    async def cut_once(self, *, idle_s: float | None = None) -> CutResult:
        """Episodes from the conversations quiet for ``idle_s`` seconds (the pause that ends an episode, by
        default); a chat that is still going is left for later."""
        quiet = GAP_S if idle_s is None else idle_s
        waiting = await self._conversations.to_cut(
            idle_before=self._clock() - timedelta(seconds=quiet), limit=CUT_CONVERSATIONS
        )
        if not waiting:
            return CutResult(0, 0, 0)
        found = await self._conversations.uncut_messages([c.id for c in waiting], limit=CUT_MESSAGES)
        made = joined = 0
        for conversation in waiting:
            plugin = self._plugin_of(conversation.channel) or ""
            for draft in cut(found[conversation.id]):
                _, created = await self.episodes.add(
                    draft, channel=conversation.channel, plugin=plugin, conversation_id=conversation.id
                )
                made += created
                joined += not created
        await self._conversations.mark_cut(
            {cid: max(m.seq for m in rows) for cid, rows in found.items() if rows}
        )
        if made:
            self._wake.set()
        return CutResult(len(waiting), made, joined)

    async def embed_once(self) -> int:
        """Vectors for one batch of the episodes that have none; how many. Zero while no embedding service is
        connected (the episodes are searched by words)."""
        service = self._embeddings()
        space = None if service is None else await service.space()
        if service is None or space is None:
            return 0
        missing = await self.episodes.missing_vectors(space, EMBED_BATCH)
        if not missing:
            self.embedding_error = None
            return 0
        vectors, made_in = await service.embed_documents(
            [ask for _, ask in missing], timeout_s=EMBED_TIMEOUT_S
        )
        await self.episodes.save_vectors(
            made_in, [(i, v) for (i, _), v in zip(missing, vectors, strict=True)]
        )
        for episode_id, _ in missing:
            await self.episodes.merge_into_nearest(episode_id, made_in, MERGE_SIMILARITY)
        self.embedding_error = None
        return len(missing)

    async def keep_cutting(self) -> None:
        """The job: cut quiet conversations, again and again."""
        while True:
            try:
                await self.cut_once()
            except Exception as err:  # the next round tries again
                self._logger.warning("scenarios not cut (%s)", type(err).__name__)
            await asyncio.sleep(CUT_EVERY_S)

    async def keep_embedding(self) -> None:
        """The job: vectors for new episodes; a wait when there is nothing to do, a longer one after a
        failure."""
        failures = 0
        while True:
            try:
                worked = await self.embed_once()
                failures = 0
            except EmbeddingUnavailableError as err:
                self.embedding_error = err.message
                wait = BACKOFF_S[min(failures, len(BACKOFF_S) - 1)]
                failures += 1
                await self._sleep(wait)
                continue
            except Exception as err:  # the next round tries again
                self._logger.warning("scenarios not embedded (%s)", type(err).__name__)
                await self._sleep(BACKOFF_S[0])
                continue
            if not worked:
                await self._sleep(EMBED_IDLE_S)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), seconds)
        self._wake.clear()

    # --- finding them ---

    def reach_of(self, channel: str | None, settings: ScenarioSettings) -> Reach | None:
        """The episodes a question on ``channel`` may use; None when none may be (the plugin or the channel is
        unknown to the scope the settings choose)."""
        if settings.scope == "agent":
            return Reach()
        if channel is None:
            return None
        if settings.scope == "channel":
            return Reach(channel=channel)
        plugin = self._plugin_of(channel)
        return None if plugin is None else Reach(plugin=plugin)

    async def search(self, question: str, reach: Reach, settings: ScenarioSettings) -> list[Hit]:
        """The episodes closest to the question: those close by meaning first, then (only while the
        embedding service is out of reach) those that share its words."""
        question = question.strip()
        service = self._embeddings()
        if service is not None:
            try:
                vector, space = await service.embed_query(question, timeout_s=QUERY_TIMEOUT_S)
            except EmbeddingUnavailableError as err:
                self.embedding_error = err.message
            else:
                self.embedding_error = None
                meaning = await self.episodes.search_vector(
                    space, vector, reach, settings.results * 3, settings.min_similarity
                )
                return _best(meaning, settings.results)
        words = await self.episodes.search_words(query_terms(question), reach, settings.results * 3)
        return _best(words, settings.results)

    async def counts(self) -> tuple[Counts, bool]:
        """How many episodes there are, how many wait for a vector, and whether the embedding service is
        connected."""
        service = self._embeddings()
        space = None if service is None else await service.space()
        return await self.episodes.counts(space), space is not None

    # --- what the agent sees ---

    def hook(self) -> PreModelHook:
        return PreModelHook("scenario_examples", self._add_examples, timeout_s=QUERY_TIMEOUT_S + 2.0)

    def tool(self) -> ToolSpec[SearchArgs]:
        return ToolSpec(
            name="scenario_search",
            description=(
                "Tìm các cuộc trò chuyện trước đây mà nhân viên đã xử lý một tình huống giống (khách hỏi gì, "
                "nhân viên đáp ra sao). Dùng để học cách đáp, không để lấy số liệu: giá và chính sách lấy từ "
                "kho tri thức."
            ),
            args_model=SearchArgs,
            handler=self._search_tool,
            timeout_s=QUERY_TIMEOUT_S + 3.0,
            max_result_chars=SHOWN_CHARS + 400,
            read_only=True,
        )

    async def examples_for(self, channel: str | None, question: str) -> str | None:
        """The block of scenarios for a question on a channel, or None when there are none to show."""
        settings = await self._settings()
        wanted = settings.scenarios
        channel_setting = settings.channels.get(channel or "")
        if not wanted.enabled or (channel_setting is not None and not channel_setting.use_scenarios):
            return None
        reach = self.reach_of(channel, wanted)
        if reach is None or len(question.strip()) < MIN_QUESTION_CHARS:
            return None
        hits = await self.search(question, reach, wanted)
        return render(hits) if hits else None

    async def _search_tool(self, args: SearchArgs, ctx: ToolContext) -> ToolOutput:
        found = await self.examples_for(ctx.channel, args.query)
        return ToolOutput(text=found or "Chưa có kịch bản nào gần giống tình huống này.")

    async def _add_examples(self, request: LlmRequest, ctx: HookContext) -> LlmRequest:
        index = _question_index(request.messages)
        if index is None:
            return request
        question = _question_text(request.messages[index])
        key = (ctx.session_id, question)
        if key not in self._cache:
            self._cache[key] = await self.examples_for(ctx.channel, question)
            while len(self._cache) > CACHE:
                self._cache.popitem(last=False)
        block = self._cache[key]
        if block is None:
            return request
        asked = request.messages[index]
        joined = asked.model_copy(update={"blocks": [*asked.blocks, TextBlock(text=f"\n\n{block}")]})
        messages = [*request.messages[:index], joined, *request.messages[index + 1 :]]
        return request.model_copy(update={"messages": messages})


def _best(hits: Sequence[Hit], results: int) -> list[Hit]:
    """The strongest hits, a question many customers asked ranking a little above one asked once."""

    def rank(hit: Hit) -> float:
        return hit.score + REPEAT_BONUS * min(hit.episode.repeats - 1, 5)

    return sorted(hits, key=rank, reverse=True)[:results]


def _question_index(messages: Sequence[Message]) -> int | None:
    """The last message that carries the customer's own words (not only the results of tools)."""
    return next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if messages[i].role == "user" and any(isinstance(b, TextBlock) for b in messages[i].blocks)
        ),
        None,
    )


def _question_text(message: Message) -> str:
    """The words of the customer: the first text block (what follows is the turn's context)."""
    return next((b.text for b in message.blocks if isinstance(b, TextBlock)), "")


def render(hits: Sequence[Hit]) -> str:
    """The scenarios as the text the agent reads, cut to a size that does not crowd out the question."""
    parts = [HEAD]
    size = len(HEAD)
    for number, hit in enumerate(hits, start=1):
        seen = f" (đã gặp {hit.episode.repeats} lần)" if hit.episode.repeats > 1 else ""
        lines = [f"### Kịch bản {number}{seen}"]
        for role, text in hit.episode.transcript:
            who = "Khách" if role == "customer" else "Nhân viên"
            lines.append(f"{who}: {text[:LINE_CHARS]}")
        block = "\n".join(lines)
        if size + len(block) > SHOWN_CHARS and number > 1:
            break
        parts.append(block)
        size += len(block)
    return "\n\n".join(parts)
