"""The case engine: a case runs its code node then its model turn and waits for the customer; the steering tools
end it or make it wait; the customer's message wakes it or stops it; the switch, the per-person cap, a lost
save and a failing node each hold; and plugins declare cases through ``ctx.register_case`` / ``ctx.cases``."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel

from agent_app.cases import MOVED_ON, NO_CASE, CaseEngine, CasesConfig, InMemoryCaseStore
from agent_app.plugins import PluginError, PluginHost, ProactiveSent, discover
from agentcore import ToolContext, ToolOutput, ToolSpec
from agentcore.cases import (
    Budget,
    CaseRecord,
    CaseSpec,
    CodeNode,
    Decision,
    Edge,
    Graph,
    StopRules,
    Trigger,
    TurnNode,
)
from agentcore.channels import PROACTIVE, InboundMessage

# 10:00 in Vietnam
NOW = datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
ON = CasesConfig(enabled=True, per_person_per_day=2)
DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"


class Quiet(BaseModel):
    unanswered: int = 0
    verdict: str = "later"


class Judge:
    """A code node whose decisions the test sets."""

    def __init__(self, *decisions: Decision | Exception) -> None:
        self.decisions = list(decisions)
        self.seen: list[Quiet] = []

    async def __call__(self, state: Quiet, now: datetime) -> Decision:
        self.seen.append(state)
        found = self.decisions.pop(0) if self.decisions else Decision()
        if isinstance(found, Exception):
            raise found
        return found


def _spec(judge: Judge, kind: str = "follow_up", **kw: Any) -> CaseSpec:
    def stop_if(state: Quiet, text: str) -> str | None:
        return "asked not to be written to" if "đừng nhắn" in text else None

    base: dict[str, Any] = {
        "kind": kind,
        "state_model": Quiet,
        "goal": lambda s: "the customer books or says no",  # pyright: ignore[reportUnknownLambdaType]
        "triggers": (Trigger("clock"), Trigger("customer_message")),
        "graph": Graph(
            start="judge",
            nodes=(CodeNode("judge", judge), TurnNode("write", lambda s, now: "write one short message")),  # pyright: ignore[reportUnknownLambdaType]
            edges=(
                Edge("judge", "write", when=lambda s: s.verdict == "later"),  # pyright: ignore[reportUnknownLambdaType]
                Edge("write", "judge", counter="unanswered"),
            ),
        ),
        "verify": lambda s: "crm_my_appointments",  # pyright: ignore[reportUnknownLambdaType]
        "stop": StopRules(max_turns=4, max_proactive=3, counters={"unanswered": 3}),
        "stop_if": stop_if,
    }
    base.update(kw)
    return CaseSpec(**base)


class FakeChat:
    """Stands in for the queue: records each turn, and lets the 'model' call a steering tool while it runs."""

    def __init__(self, engine_tools: list[ToolSpec[Any]], counted: bool = True) -> None:
        self.tools = {t.name: t for t in engine_tools}
        self.counted = counted
        self.turns: list[dict[str, str]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.outputs: list[ToolOutput] = []

    async def send_to(
        self, *, channel: str, conversation_id: str, user_id: str, message_id: str, instruction: str
    ) -> ProactiveSent:
        self.turns.append({"channel": channel, "message_id": message_id, "instruction": instruction})
        ctx = ToolContext(
            session_id="s1", channel=channel, conversation_id=conversation_id, message_id=message_id, now=NOW
        )
        for name, args in self.calls:
            spec = self.tools[name]
            self.outputs.append(await spec.handler(spec.args_model.model_validate(args), ctx))
        self.calls = []
        return ProactiveSent(self.counted)


class Setup:
    def __init__(self, *specs: CaseSpec, config: CasesConfig = ON, counted: bool = True) -> None:
        self.store = InMemoryCaseStore()
        self.now = NOW
        self.config = config
        self.specs = {s.kind: ("demo", s) for s in specs}
        self.engine = CaseEngine(
            self.store,
            lambda: self.specs,
            config=lambda: self.config,
            zone=lambda: ZONE,
            clock=lambda: self.now,
        )
        self.chat = FakeChat(self.engine.tools(), counted)

        async def session_for(channel: str, conversation_id: str) -> str:
            return f"session-{conversation_id}"

        self.engine.attach(self.chat, session_for)

    async def open(self, kind: str = "follow_up", key: str = "c1", user: str = "u1") -> CaseRecord:
        return await self.engine.open_for(
            "demo", kind, key, channel="zalo-a", conversation_id=key, user_id=user, state=Quiet()
        )

    async def events(self, case_id: int) -> list[str]:
        return [e["kind"] for e in await self.store.events(case_id)]


def _inbound(text: str, conversation_id: str = "c1", **metadata: str) -> InboundMessage:
    return InboundMessage(
        channel="zalo-a",
        conversation_id=conversation_id,
        user_id="u1",
        message_id=f"m-{text}",
        text=text,
        metadata=metadata,
    )


async def test_a_case_runs_its_code_node_then_writes_and_waits_for_the_customer() -> None:
    judge = Judge()
    s = Setup(_spec(judge))
    case = await s.open()
    assert (case.status, case.node, case.session_id) == ("open", "judge", "session-c1")

    assert await s.engine.pass_once() == 1

    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.wait_for, after.node) == ("waiting", "customer", "judge")
    assert (after.turns, after.proactive_sent, after.state["unanswered"]) == (1, 1, 1)
    [turn] = s.chat.turns
    assert turn["message_id"] == f"case:{case.id}:0"
    assert turn["instruction"].startswith("[Case · follow_up] Goal: the customer books or says no")
    assert await s.events(case.id) == ["opened", "decision", "sent", "decision"]


async def test_opening_the_same_case_twice_keeps_one() -> None:
    s = Setup(_spec(Judge()))
    first = await s.open()
    second = await s.open()
    assert first.id == second.id
    assert await s.events(first.id) == ["opened"]


async def test_case_done_in_the_turn_closes_the_case() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    s.chat.calls = [("case_done", {"reason": "crm says confirmed"})]
    await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.end_reason) == ("done", "crm says confirmed")
    assert not s.chat.outputs[0].is_error


async def test_case_wait_until_in_the_turn_sets_the_wake_up() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    at = NOW + timedelta(days=1)
    s.chat.calls = [("case_wait_until", {"wait_for": "clock", "until": at.isoformat(), "why": "call back"})]
    await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.wait_for, after.wake_at) == ("waiting", "clock", at)
    assert await s.engine.pass_once() == 0  # not due yet
    s.now = at
    assert await s.engine.pass_once() == 1


async def test_outside_a_case_the_steering_tools_refuse() -> None:
    s = Setup(_spec(Judge()))
    done = s.chat.tools["case_done"]
    out = await done.handler(
        done.args_model.model_validate({"reason": "x"}),
        ToolContext(session_id="s1", channel="zalo-a", conversation_id="c1"),
    )
    assert (out.is_error, out.text) == (True, NO_CASE)


async def test_only_the_cases_own_turn_in_its_own_chat_can_steer_it() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    await s.engine.pass_once()  # turn 0 ran; the case now waits at turn 1
    done = s.chat.tools["case_done"]
    args = done.args_model.model_validate({"reason": "x"})

    def ctx(message_id: str, conversation_id: str = "c1") -> ToolContext:
        return ToolContext(
            session_id="s1", channel="zalo-a", conversation_id=conversation_id, message_id=message_id
        )

    customer = await done.handler(args, ctx("zalo-msg-123"))
    other_chat = await done.handler(args, ctx(f"case:{case.id}:1", conversation_id="c9"))
    old_turn = await done.handler(args, ctx(f"case:{case.id}:0"))
    assert [(o.is_error, o.text) for o in (customer, other_chat, old_turn)] == [
        (True, NO_CASE),
        (True, MOVED_ON),
        (True, MOVED_ON),
    ]
    after = await s.store.get(case.id)
    assert after is not None
    assert after.status == "waiting"


async def test_a_decision_outlives_the_engine_that_ran_the_turn() -> None:
    """The service stops after the model decided but before the case was saved: a new engine on the same store
    sends the same turn again (the queue hands back the one already run) and reads the decision kept for it."""
    s = Setup(_spec(Judge()))
    case = await s.open()

    async def dies(**kw: str) -> ProactiveSent:
        await FakeChat.send_to(s.chat, **kw)  # the turn runs and the model calls case_done
        raise RuntimeError("service stopped")

    s.chat.calls = [("case_done", {"reason": "crm says confirmed"})]
    s.chat.send_to = dies  # type: ignore[method-assign]
    await s.engine.pass_once()
    stuck = await s.store.get(case.id)
    assert stuck is not None
    assert (stuck.status, stuck.turns) == ("waiting", 0)

    again = Setup(_spec(Judge()))
    again.store = s.store
    again.engine = CaseEngine(
        s.store,
        lambda: again.specs,
        config=lambda: ON,
        zone=lambda: ZONE,
        clock=lambda: NOW + timedelta(minutes=5),
    )
    again.chat = FakeChat(again.engine.tools())

    async def session_for(channel: str, conversation_id: str) -> str:
        return "s1"

    again.engine.attach(again.chat, session_for)
    await again.engine.pass_once()

    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.end_reason, after.turns) == ("done", "crm says confirmed", 1)
    assert [t["message_id"] for t in [*s.chat.turns, *again.chat.turns]] == [f"case:{case.id}:0"] * 2


async def test_the_customer_writing_wakes_the_case() -> None:
    judge = Judge(Decision(), Decision(patch={"verdict": "booked"}))
    s = Setup(_spec(judge))
    case = await s.open()
    await s.engine.pass_once()
    s.now = NOW + timedelta(minutes=10)
    await s.engine.on_inbound(_inbound("mai em qua nhé"))
    woken = await s.store.get(case.id)
    assert woken is not None
    assert woken.wake_at == s.now
    await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.end_reason) == ("done", "end of the graph")
    assert len(judge.seen) == 2


async def test_a_customer_who_asks_to_stop_ends_the_case_before_any_node() -> None:
    judge = Judge()
    s = Setup(_spec(judge))
    case = await s.open()
    await s.engine.pass_once()
    await s.engine.on_inbound(_inbound("thôi đừng nhắn nữa"))
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.end_reason) == ("stopped", "asked not to be written to")
    assert len(judge.seen) == 1


async def test_group_and_proactive_messages_wake_nothing() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    await s.engine.pass_once()
    before = await s.store.get(case.id)
    await s.engine.on_inbound(_inbound("đừng nhắn", thread_type="group"))
    await s.engine.on_inbound(_inbound("đừng nhắn", **{PROACTIVE: "1"}))
    assert await s.store.get(case.id) == before


async def test_the_switch_off_runs_nothing_and_closes_nothing() -> None:
    s = Setup(_spec(Judge()), config=CasesConfig(enabled=False))
    case = await s.open()
    assert await s.engine.pass_once() == 0
    assert s.chat.turns == []
    after = await s.store.get(case.id)
    assert after is not None
    assert after.status == "open"


async def test_the_daily_cap_of_a_person_counts_every_kind_of_case() -> None:
    s = Setup(_spec(Judge()), _spec(Judge(), kind="reminder"), config=CasesConfig(True, per_person_per_day=1))
    first = await s.open()
    await s.engine.pass_once()
    second = await s.open(kind="reminder", key="c2")
    await s.engine.pass_once()
    held = await s.store.get(second.id)
    assert held is not None
    assert (held.status, held.wait_for, held.node) == ("waiting", "clock", "write")
    assert held.wake_at == datetime(2026, 10, 23, tzinfo=ZONE)
    assert [t["message_id"] for t in s.chat.turns] == [f"case:{first.id}:0"]
    assert "blocked" in await s.events(second.id)


async def test_a_skipped_message_does_not_count_but_the_case_still_waits() -> None:
    s = Setup(_spec(Judge()), counted=False)
    case = await s.open()
    await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.wait_for, after.turns, after.proactive_sent) == ("waiting", "customer", 1, 0)
    assert "sent" not in await s.events(case.id)


async def test_room_today_is_the_cap_blocked_checks_less_what_every_case_sent() -> None:
    setup = Setup(_spec(Judge(), budget=Budget(per_person_per_day=3)), _spec(Judge(), kind="other"))
    assert await setup.engine.room_today("demo", "follow_up", "zalo-a", "u1") == 2  # the setting lowers 3

    await setup.open()
    await setup.engine.pass_once()  # the follow-up writes once

    assert await setup.engine.room_today("demo", "other", "zalo-a", "u1") == 1
    assert await setup.engine.room_today("demo", "other", "zalo-a", "u2") == 2
    setup.config = CasesConfig(enabled=True, per_person_per_day=1)
    assert await setup.engine.room_today("demo", "follow_up", "zalo-a", "u1") == 0


async def test_a_save_on_a_stale_version_is_dropped() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    newer = await s.store.save(replace(case, goal="changed elsewhere"))
    assert newer is not None
    result = await s.engine.step(case, ON)  # the old copy
    assert result == case
    current = await s.store.get(case.id)
    assert current == newer
    assert "lost" in await s.events(case.id)


async def test_a_failing_node_is_tried_again_later() -> None:
    s = Setup(_spec(Judge(RuntimeError("crm down"))))
    case = await s.open()
    await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.node, after.wake_at) == ("waiting", "judge", NOW + timedelta(minutes=5))
    assert "error" in await s.events(case.id)


async def test_the_counter_cap_ends_the_loop() -> None:
    """Three unanswered messages end it (the daily cap is raised so only the counter decides)."""
    s = Setup(
        _spec(Judge(), budget=Budget(per_person_per_day=5)), config=CasesConfig(True, per_person_per_day=5)
    )
    case = await s.open()
    for minutes in (0, 10, 20):
        s.now = NOW + timedelta(minutes=minutes)
        await s.engine.on_inbound(_inbound(f"ừ {minutes}"))
        await s.engine.pass_once()
    after = await s.store.get(case.id)
    assert after is not None
    assert (after.status, after.end_reason, after.proactive_sent) == ("stopped", "unanswered reached 3", 3)


async def test_a_plugin_opens_only_its_own_kinds() -> None:
    s = Setup(_spec(Judge()))
    with pytest.raises(ValueError, match="no case"):
        await s.engine.open_for(
            "other", "follow_up", "k", channel="zalo-a", conversation_id="c1", user_id="u1", state=Quiet()
        )


# --- the plugin contract ---

CASE_PLUGIN = """
from pydantic import BaseModel

from agentcore.cases import CaseSpec, CodeNode, Decision, Graph, Trigger


class State(BaseModel):
    pass


async def judge(state, now):
    return Decision()


def register(ctx):
    for kind in ctx.config.get("kinds", ["ping"]):
        ctx.register_case(
            CaseSpec(
                kind=kind,
                state_model=State,
                goal=lambda s: "g",
                triggers=(Trigger("clock"),),
                graph=Graph("judge", (CodeNode("judge", judge),)),
                verify=lambda s: "v",
            )
        )
    if ctx.config.get("use"):
        ctx.cases
"""


def _host(tmp_path: Path, *names: str) -> PluginHost:
    for name in names:
        folder = tmp_path / name
        folder.mkdir(parents=True)
        (folder / "plugin.toml").write_text(f'name = "{name}"\n', encoding="utf-8")
        (folder / "__init__.py").write_text(textwrap.dedent(CASE_PLUGIN), encoding="utf-8")
    return PluginHost(discover([("agent", tmp_path)]).plugins, {})


def test_a_plugin_declares_its_cases_and_they_go_with_it(tmp_path: Path) -> None:
    host = _host(tmp_path, "a")
    host.enable("a")
    assert [(plugin, spec.kind) for plugin, spec in host.contributions().cases] == [("a", "ping")]
    host.disable("a")
    assert host.contributions().cases == ()


def test_a_kind_of_case_belongs_to_one_plugin(tmp_path: Path) -> None:
    host = _host(tmp_path, "a", "b")
    host.enable("a")
    with pytest.raises(PluginError, match="case ping already comes from a"):
        host.enable("b")
    with pytest.raises(PluginError, match="registered twice"):
        host.enable("b", {"kinds": ["x", "x"]})


def test_ctx_cases_needs_a_running_engine(tmp_path: Path) -> None:
    host = _host(tmp_path, "a")
    with pytest.raises(PluginError, match="runs no cases"):
        host.enable("a", {"use": True})


def test_the_steering_tools_come_only_with_a_plugin_that_declares_cases(tmp_path: Path) -> None:
    from agent_app.profile import load_profile
    from agent_app.runtime import build_runtime

    host = _host(tmp_path, "a")
    runtime = build_runtime(
        load_profile(Path(__file__).resolve().parents[1] / "agents" / "dev"),
        fake=True,
        env={},
        db=None,
        plugins=host,
    )
    steering = {"case_done", "case_wait_until"}
    assert not steering & set(runtime.agent.tools.names())
    host.enable("a", {"use": True})  # ctx.cases works: the runtime gave the host its engine
    assert steering <= set(runtime.agent.tools.names())
    host.disable("a")
    assert not steering & set(runtime.agent.tools.names())


# --- run now, by an admin ---


async def test_an_admin_runs_a_waiting_case_now_and_its_checks_still_run() -> None:
    judge = Judge()
    s = Setup(_spec(judge))
    case = await s.open()
    later = (NOW + timedelta(days=1)).isoformat()
    s.chat.calls = [("case_wait_until", {"wait_for": "clock", "until": later, "why": "call back"})]
    await s.engine.pass_once()
    assert await s.engine.pass_once() == 0  # not due yet

    assert await s.engine.wake_by_hand(case.id)

    woken = await s.store.get(case.id)
    assert woken is not None
    assert woken.wake_at == NOW
    assert (await s.store.events(case.id))[-1]["detail"]["by"] == "admin"
    assert await s.engine.pass_once() == 1
    assert len(judge.seen) == 2  # the code node ran again before the turn


async def test_run_now_refuses_a_closed_case_an_unknown_one_and_one_whose_plugin_is_off() -> None:
    s = Setup(_spec(Judge()))
    case = await s.open()
    s.chat.calls = [("case_done", {"reason": "booked"})]
    await s.engine.pass_once()
    other = await s.open(key="c2")

    assert not await s.engine.wake_by_hand(case.id)
    assert not await s.engine.wake_by_hand(999)
    s.specs = {}
    assert not await s.engine.wake_by_hand(other.id)


async def test_the_run_now_route_wakes_a_live_case_and_refuses_the_others() -> None:
    import httpx

    from agent_app.gateway import GatewaySettings, create_app
    from agent_app.profile import load_profile
    from agent_app.runtime import build_runtime

    s = Setup(_spec(Judge()))
    live = await s.open()
    closed = await s.open(key="c2")
    done = await s.store.get(closed.id)
    assert done is not None
    await s.store.save(replace(done, status="done"))
    admin = "a" * 40
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    dispatcher = runtime.dispatcher()
    app = create_app(dispatcher, GatewaySettings(token="t" * 40, admin_token=admin), cases=s.engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://agent",
        headers={"Authorization": f"Bearer {admin}"},
    ) as client:
        woken = await client.post(f"/v1/admin/cases/{live.id}/wake")
        refused = await client.post(f"/v1/admin/cases/{closed.id}/wake")
        missing = await client.post("/v1/admin/cases/999/wake")
        anonymous = await client.post(f"/v1/admin/cases/{live.id}/wake", headers={"Authorization": ""})
    await dispatcher.close(grace_s=1.0)

    assert (woken.status_code, woken.json()["id"]) == (200, live.id)
    assert (refused.status_code, refused.json()["error"]["kind"]) == (409, "not_live")
    assert missing.status_code == 404
    assert anonymous.status_code == 401


# --- send a test now, by an admin ---


async def _waiting_a_day(s: Setup) -> CaseRecord:
    case = await s.open()
    later = (NOW + timedelta(days=1)).isoformat()
    s.chat.calls = [("case_wait_until", {"wait_for": "clock", "until": later, "why": "call back"})]
    await s.engine.pass_once()
    before = await s.store.get(case.id)
    assert before is not None
    return before


async def test_a_test_send_writes_once_now_and_leaves_the_case_as_it_was() -> None:
    s = Setup(_spec(Judge()))
    before = await _waiting_a_day(s)

    outcome = await s.engine.try_now(before.id)

    assert outcome is not None
    assert (outcome.sent, outcome.why) == (True, "")
    assert s.chat.turns[-1]["message_id"].startswith(f"case-try:{before.id}:")
    after = await s.store.get(before.id)
    assert after is not None
    fields = ("status", "node", "wait_for", "wake_at", "state", "turns", "proactive_sent", "version")
    assert [getattr(after, f) for f in fields] == [getattr(before, f) for f in fields]
    assert (await s.store.events(before.id))[-1]["detail"]["by"] == "admin_try"


async def test_a_test_turn_cannot_steer_the_case() -> None:
    s = Setup(_spec(Judge()))
    before = await _waiting_a_day(s)
    s.chat.calls = [("case_done", {"reason": "booked"})]

    await s.engine.try_now(before.id)

    assert s.chat.outputs[-1].is_error
    after = await s.store.get(before.id)
    assert after is not None
    assert after.status == "waiting"


async def test_a_test_send_keeps_the_shared_limits_and_counts_in_the_daily_cap() -> None:
    s = Setup(_spec(Judge()), config=CasesConfig(enabled=True, per_person_per_day=2))
    before = await _waiting_a_day(s)  # one message sent today

    first = await s.engine.try_now(before.id)
    second = await s.engine.try_now(before.id)
    s.config = CasesConfig(enabled=False)
    third = await s.engine.try_now(before.id)

    assert [(o.sent, o.why) if o else None for o in (first, second, third)] == [
        (True, ""),
        (False, "person_daily_cap"),
        (False, "disabled"),
    ]
    assert len(s.chat.turns) == 2


async def test_the_test_send_route_answers_what_happened() -> None:
    import httpx

    from agent_app.gateway import GatewaySettings, create_app
    from agent_app.profile import load_profile
    from agent_app.runtime import build_runtime

    s = Setup(_spec(Judge()))
    live = await _waiting_a_day(s)
    closed = await s.open(key="c2")
    done = await s.store.get(closed.id)
    assert done is not None
    await s.store.save(replace(done, status="done"))
    admin = "a" * 40
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    dispatcher = runtime.dispatcher()
    app = create_app(dispatcher, GatewaySettings(token="t" * 40, admin_token=admin), cases=s.engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://agent",
        headers={"Authorization": f"Bearer {admin}"},
    ) as client:
        tried = await client.post(f"/v1/admin/cases/{live.id}/try")
        refused = await client.post(f"/v1/admin/cases/{closed.id}/try")
        missing = await client.post("/v1/admin/cases/999/try")
    await dispatcher.close(grace_s=1.0)

    assert (tried.status_code, tried.json()) == (200, {"sent": True, "why": ""})
    assert (refused.status_code, refused.json()["error"]["kind"]) == (409, "not_live")
    assert missing.status_code == 404
