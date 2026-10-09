"""Recording a model's calls into a cassette and playing them back: the same results, deltas and errors, and a
loud failure when the run drifts from the recording."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from agentcore import (
    AssistantResult,
    InMemorySessionStore,
    LlmRequest,
    ModelClient,
    ModelError,
    PromptBuilder,
    ToolContext,
    ToolOutput,
    ToolRegistry,
    ToolSpec,
    TurnResult,
    run_turn,
)
from agentcore.harness.model.replay import (
    Cassette,
    CassetteError,
    CassetteWriter,
    RecordingModel,
    ReplayModel,
)
from agentcore.harness.model.scripted import ScriptedModel, calls, reply, tool_call


class AddArgs(BaseModel):
    a: int
    b: int


async def _add(args: AddArgs, ctx: ToolContext) -> ToolOutput:
    return ToolOutput(text=str(args.a + args.b))


ADD = ToolSpec(name="add", description="Add.", args_model=AddArgs, handler=_add)


async def _turn(model: ModelClient, text: str, store: InMemorySessionStore | None = None) -> TurnResult:
    async def no_wait(seconds: float) -> None:
        return None

    return await run_turn(
        session_id="s",
        user_text=text,
        prompt=PromptBuilder.fixed("sys"),
        model=model,
        tools=ToolRegistry([ADD]),
        store=store or InMemorySessionStore(),
        sleep=no_wait,
    )


def _transient(request: LlmRequest) -> AssistantResult:
    raise ModelError("transient", "reset", retry_after_s=0.0)


async def _record(path: Path) -> TurnResult:
    writer = CassetteWriter(path, model="scripted")
    inner = ScriptedModel([calls(tool_call("add", {"a": 2, "b": 3})), _transient, reply("5")])
    writer.turn("2+3?")
    return await _turn(RecordingModel(inner, writer), "2+3?")


async def test_a_recorded_turn_replays_to_the_same_result(tmp_path: Path) -> None:
    path = tmp_path / "cassette.jsonl"
    recorded = await _record(path)

    cassette = Cassette.load(path)
    replayed_model = ReplayModel(cassette)
    replayed = await _turn(replayed_model, cassette.turns[0])
    replayed_model.assert_consumed()

    assert (cassette.header.model, cassette.turns) == ("scripted", ["2+3?"])
    assert [c.error.kind if c.error else "ok" for c in cassette.calls] == ["ok", "transient", "ok"]
    assert cassette.calls[0].request.tools == ["add"]
    assert cassette.calls[0].request.user == "2+3?"
    assert (replayed.text, replayed.steps) == (recorded.text, recorded.steps)
    assert [m.model_dump() for m in replayed.new_messages] == [m.model_dump() for m in recorded.new_messages]
    assert "sys" not in path.read_text(encoding="utf-8")


async def test_a_drifting_request_and_extra_or_missing_calls_fail_loud(tmp_path: Path) -> None:
    path = tmp_path / "cassette.jsonl"
    await _record(path)

    with pytest.raises(CassetteError, match="user was '2\\+3\\?' when recorded, now '9\\+9\\?'"):
        await _turn(ReplayModel(Cassette.load(path)), "9+9?")
    short = ReplayModel(Cassette.load(path))
    await _turn(short, "2+3?")
    with pytest.raises(CassetteError, match="called 4 times, the cassette has 3"):
        await short.complete(LlmRequest(system="", messages=[]))
    unused = ReplayModel(Cassette.load(path))
    with pytest.raises(CassetteError, match="3 recorded model call"):
        unused.assert_consumed()


async def test_a_hand_edited_error_line_replays_as_that_error(tmp_path: Path) -> None:
    path = tmp_path / "cassette.jsonl"
    await _record(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    last.pop("result")
    last["error"] = {"kind": "auth", "message": "key revoked"}
    path.write_text("\n".join([*lines[:-1], json.dumps(last)]) + "\n", encoding="utf-8")

    with pytest.raises(ModelError) as caught:
        await _turn(ReplayModel(Cassette.load(path)), "2+3?")

    assert (caught.value.kind, str(caught.value)) == ("auth", "key revoked")


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("", "is empty"),
        ('{"type": "turn", "user_text": "x"}\n', "does not start with a header"),
        ('{"type": "header", "format": 99}\n', "format 99"),
        ('{"type": "header"}\n{"type": "call"}\n', "exactly one of result and error"),
    ],
)
def test_a_broken_cassette_is_refused(tmp_path: Path, content: str, error: str) -> None:
    path = tmp_path / "cassette.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(CassetteError, match=error):
        Cassette.load(path)
