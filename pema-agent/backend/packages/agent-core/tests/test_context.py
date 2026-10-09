"""Token estimates, the compaction policy, where history is cut, the summary and compaction inside a turn."""

from __future__ import annotations

from typing import Any

import pytest

from agentcore import (
    AssistantResult,
    CompactionRecord,
    CompactionResult,
    ContextManager,
    ContextPolicy,
    InMemorySessionStore,
    LlmRequest,
    LoopPolicy,
    Message,
    ModelError,
    PromptBuilder,
    TextBlock,
    TokenEstimator,
    ToolRegistry,
    ToolResultBlock,
    ToolSchema,
    ToolUseBlock,
    TurnResult,
    Usage,
    run_turn,
)
from agentcore.context import choose_cut
from agentcore.context.compaction import (
    FALLBACK_NOTE,
    SUMMARY_SYSTEM,
    TRANSCRIPT_BLOCK_CHARS,
    TRUNCATED_NOTE,
    render_transcript,
)
from agentcore.harness.model.scripted import ScriptedModel, reply
from agentcore.prompt.builder import SUMMARY_OPEN

T, S = "t", "s1"
ESTIMATOR = TokenEstimator()


def _assistant(*blocks: TextBlock | ToolUseBlock) -> Message:
    return Message(role="assistant", blocks=list(blocks))


def _result(call_id: str, content: str = "ok") -> Message:
    return Message(role="tool", blocks=[ToolResultBlock(tool_use_id=call_id, name="t", content=content)])


# u0 a0 | u1 a1(call) t1 a1' | u2 a2 : turns start at 0, 2 and 6
HISTORY = [
    Message.user("first question"),
    _assistant(TextBlock(text="first answer")),
    Message.user("second question"),
    _assistant(ToolUseBlock(id="c1", name="t", args={"q": 1})),
    _result("c1"),
    _assistant(TextBlock(text="second answer")),
    Message.user("third question"),
    _assistant(TextBlock(text="third answer")),
]


def test_tokens_are_estimated_from_characters_with_a_per_message_overhead() -> None:
    assert ESTIMATOR.text("abcdefg") == 3
    assert ESTIMATOR.message(Message.user("abcdef")) == 4 + 2
    call = _assistant(ToolUseBlock(id="c", name="add", args={"a": 1}))
    assert ESTIMATOR.message(call) == 4 + ESTIMATOR.text('add {"a": 1}')
    tool = ToolSchema(name="t", description="d", parameters={})
    request = LlmRequest(system="abc", messages=[Message.user("abc")], tools=[tool])
    assert ESTIMATOR.request(request) == 1 + (4 + 1) + ESTIMATOR.text("t d {}")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_tokens": 0},
        {"window_tokens": 10, "compact_at": 0.0},
        {"window_tokens": 10, "compact_at": 1.5},
        {"window_tokens": 10, "keep_recent_ratio": 1.0},
        {"window_tokens": 10, "chars_per_token": 0.0},
    ],
)
def test_a_context_policy_refuses_impossible_values(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="must be"):
        ContextPolicy(**kwargs)


def test_the_threshold_leaves_room_for_the_reply() -> None:
    policy = ContextPolicy(window_tokens=1000, compact_at=0.75, keep_recent_ratio=0.2)

    assert policy.threshold(200) == 600
    assert policy.keep_budget(200) == 120
    assert policy.threshold(5000) == 0


def test_the_cut_keeps_as_many_recent_turns_as_the_budget_allows() -> None:
    def cut(budget: int, keep_from: int = 8, start: int = 0) -> int | None:
        return choose_cut(HISTORY, start=start, keep_from=keep_from, keep_budget=budget, estimator=ESTIMATOR)

    assert cut(10_000) == 2
    assert cut(ESTIMATOR.messages(HISTORY[6:])) == 6
    assert cut(0) == 6
    assert cut(0, keep_from=6) == 6
    assert cut(0, keep_from=5) == 2
    assert cut(0, start=2) == 6
    assert cut(0, start=6) is None


def test_the_cut_only_falls_on_a_user_message_so_tool_pairs_stay_together() -> None:
    for budget in range(0, ESTIMATOR.messages(HISTORY) + 1, 3):
        point = choose_cut(HISTORY, start=0, keep_from=8, keep_budget=budget, estimator=ESTIMATOR)
        assert point is not None
        assert HISTORY[point].role == "user"


def test_a_single_turn_has_nothing_to_cut() -> None:
    assert choose_cut(HISTORY[:2], start=0, keep_from=2, keep_budget=0, estimator=ESTIMATOR) is None
    assert choose_cut([], start=0, keep_from=0, keep_budget=0, estimator=ESTIMATOR) is None


def test_the_transcript_shows_calls_results_and_clips_long_text() -> None:
    error = Message(
        role="tool", blocks=[ToolResultBlock(tool_use_id="c2", name="t", content="down", is_error=True)]
    )
    text = render_transcript([*HISTORY[2:5], error, Message.user("x" * (TRANSCRIPT_BLOCK_CHARS + 5))])

    assert text.splitlines()[:4] == [
        "[user] second question",
        '[assistant called t] {"q": 1}',
        "[tool result t] ok",
        "[tool error t] down",
    ]
    assert text.endswith("…[5 more chars]")


async def _store_with(messages: list[Message]) -> InMemorySessionStore:
    store = InMemorySessionStore()
    for message in messages:
        await store.append(T, S, message)
    return store


def _manager(model: ScriptedModel, *, window: int = 10_000, keep: float = 0.0) -> ContextManager:
    policy = ContextPolicy(window_tokens=window, compact_at=1.0, keep_recent_ratio=keep)
    return ContextManager(policy, model)


async def _compact(
    manager: ContextManager, store: InMemorySessionStore, keep_from: int = 8, *, force: bool = False
) -> CompactionResult | None:
    return await manager.compact(
        store=store, tenant_id=T, session_id=S, keep_from=keep_from, max_output_tokens=0, force=force
    )


async def test_a_compaction_summarises_the_older_turns_and_keeps_the_rest() -> None:
    model = ScriptedModel([reply("## Goal\nanswer questions", input_tokens=50, output_tokens=10)])
    store = await _store_with(HISTORY)

    outcome = await _compact(_manager(model), store)

    assert outcome is not None
    assert outcome.record == CompactionRecord(summary="## Goal\nanswer questions", first_kept=6)
    assert (outcome.compacted_messages, outcome.fallback, outcome.usage.input_tokens) == (6, False, 50)
    assert await store.load_compaction(T, S) == outcome.record
    assert len(await store.load(T, S)) == len(HISTORY)
    (request,) = model.requests
    assert (request.system, request.tools) == (SUMMARY_SYSTEM, [])
    sent = request.messages[0].text()
    assert sent.startswith("<transcript>\n[user] first question")
    assert "third question" not in sent


async def test_a_later_compaction_folds_in_the_previous_summary() -> None:
    model = ScriptedModel([reply("merged")])
    store = await _store_with([*HISTORY, Message.user("fourth"), _assistant(TextBlock(text="4"))])
    await store.save_compaction(T, S, CompactionRecord(summary="old summary", first_kept=2))

    outcome = await _compact(_manager(model), store, keep_from=10)

    assert outcome is not None
    assert outcome.record.first_kept == 8
    sent = model.requests[0].messages[0].text()
    assert sent.startswith("<previous-summary>\nold summary\n</previous-summary>")
    assert "[user] second question" in sent
    assert "first question" not in sent


def _fails(request: LlmRequest) -> AssistantResult:
    raise ModelError("transient", "down")


def _cut_short(request: LlmRequest) -> AssistantResult:
    message = Message(role="assistant", blocks=[TextBlock(text="partial")], usage=Usage())
    return AssistantResult(message=message, stop_reason="max_tokens")


async def test_a_failed_or_empty_summary_drops_the_turns_with_a_note() -> None:
    failed = await _compact(_manager(ScriptedModel([_fails])), await _store_with(HISTORY))
    assert failed is not None
    assert (failed.record.summary, failed.fallback) == (FALLBACK_NOTE, True)

    store = await _store_with(HISTORY)
    await store.save_compaction(T, S, CompactionRecord(summary="old summary", first_kept=2))
    empty = await _compact(_manager(ScriptedModel([reply("  ")])), store)
    assert empty is not None
    assert (empty.record.summary, empty.fallback) == (f"old summary\n\n{FALLBACK_NOTE}", True)


async def test_a_summary_cut_short_is_marked() -> None:
    outcome = await _compact(_manager(ScriptedModel([_cut_short])), await _store_with(HISTORY))

    assert outcome is not None
    assert outcome.record.summary == f"partial\n{TRUNCATED_NOTE}"


async def test_nothing_to_compact_saves_nothing() -> None:
    store = await _store_with(HISTORY[:2])

    assert await _compact(_manager(ScriptedModel([])), store, keep_from=2, force=True) is None


async def test_a_turn_over_budget_compacts_first_and_the_next_turn_reuses_the_summary() -> None:
    big = "x" * 3_000
    store = await _store_with(
        [
            Message.user(big),
            _assistant(TextBlock(text=big)),
            Message.user(big),
            _assistant(TextBlock(text="ok")),
        ]
    )
    model = ScriptedModel(
        [reply("SUMMARY", input_tokens=7), reply("answer", input_tokens=3), reply("again", input_tokens=2)]
    )
    manager = _manager(model, window=1_100)
    prompt = PromptBuilder.fixed("sys")

    async def turn(text: str) -> TurnResult:
        return await run_turn(
            session_id=S,
            user_text=text,
            prompt=prompt,
            model=model,
            tools=ToolRegistry(),
            store=store,
            policy=LoopPolicy(max_output_tokens=100),
            tenant_id=T,
            context=manager,
        )

    first = await turn("now")
    second = await turn("later")

    assert (first.text, first.compactions, first.usage.input_tokens) == ("answer", 1, 10)
    assert second.compactions == 0
    summarise, answer, again = model.requests
    assert summarise.system == SUMMARY_SYSTEM
    assert answer.system == again.system
    assert answer.system.startswith(f"sys\n\n{SUMMARY_OPEN}")
    assert "SUMMARY" in answer.system
    assert [m.text() for m in answer.messages] == ["now"]
    assert [m.text() for m in again.messages] == ["now", "answer", "later"]
    assert len(await store.load(T, S)) == 8


async def test_without_a_context_manager_nothing_is_compacted() -> None:
    store = await _store_with([Message.user("x" * 50_000), _assistant(TextBlock(text="ok"))])
    model = ScriptedModel([reply("fine")])

    result = await run_turn(
        session_id=S,
        user_text="hi",
        prompt=PromptBuilder.fixed("sys"),
        model=model,
        tools=ToolRegistry(),
        store=store,
        tenant_id=T,
    )

    assert result.compactions == 0
    assert len(model.requests[0].messages) == 3
