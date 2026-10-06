"""Tests of the ops eval itself (package O, step O7). New tests, no zalo-agent original.

No database, no network, no sleep: they check the invariants the load eval measures (gap compliance per identity,
the cap counting proactive sends only, every sender served, the bell staying quiet after an ack, escalation
reaching the 24/7 contact, no model call) and that the report says "not run" instead of inventing a number."""

from __future__ import annotations

import pytest

from evals.care.stats import percentile
from evals.ops.measure_escalation import measure_escalation
from evals.ops.measure_notify import NotifyParameters, measure_notify
from evals.ops.measure_queue import (
    AGENT,
    SCHEDULER,
    IdentityScenario,
    LoadParameters,
    Request,
    build_scenarios,
    measure_queue,
    operator_name,
    simulate_identity,
)
from evals.ops.report import OpsResults, render
from evals.ops.run_eval import safety_failures
from pema_contracts.ops import NotificationProvider


# -------------------------------------------------------------------------------------------- queue
async def test_the_scenario_is_deterministic_and_has_the_traffic_it_says() -> None:
    params = LoadParameters()
    long, hoa = build_scenarios(params)
    assert build_scenarios(params) == (long, hoa)
    senders = [request.sender for request in long.requests]
    assert len(long.requests) == params.threads + params.agent_replies + params.reminders
    assert senders.count(AGENT) == params.agent_replies
    assert senders.count(SCHEDULER) == params.reminders
    assert {operator_name(i) for i in range(params.operators)} <= set(senders)
    assert [request.proactive for request in long.requests].count(True) == params.reminders
    assert len(hoa.requests) == params.other_identity_replies


async def test_no_message_leaves_less_than_the_minimum_gap_after_the_one_before_on_any_identity() -> None:
    report = await measure_queue()
    assert report.violations == 0
    for result in (*report.timed, report.burst):
        assert result.sent > 0
        assert result.gaps, result.account_id
        assert min(result.gaps) >= result.gap_min_s - 1e-6, result.account_id


async def test_every_operator_and_the_agent_are_served_and_only_proactive_messages_meet_the_cap() -> None:
    report = await measure_queue()
    params = report.parameters
    long = report.timed[0]
    assert long.rejected_other == 0
    assert long.rejected_cap == params.reminders - (params.daily_cap or 0)
    served = {leave.sender for leave in long.leaves}
    assert served == {operator_name(i) for i in range(params.operators)} | {AGENT, SCHEDULER}
    replies = [leave for leave in long.leaves if not leave.proactive]
    assert len(replies) == params.threads + params.agent_replies, "no reply was refused by the cap"
    assert sum(1 for leave in long.leaves if leave.proactive) == params.daily_cap


async def test_an_identity_with_a_short_gap_does_not_wait_for_one_with_a_long_gap() -> None:
    report = await measure_queue()
    long, hoa = report.timed
    assert max(hoa.waits) < percentile(long.waits_of(AGENT), 50), (
        "the quiet identity is not queued behind the busy one"
    )


async def test_the_gap_is_shared_by_the_agent_and_the_operators_not_one_gap_each() -> None:
    requests = (
        Request(0.0, AGENT),
        Request(0.0, operator_name(0)),
        Request(0.0, operator_name(1)),
    )
    scenario = IdentityScenario("long", 20, 20, None, requests)
    result = await simulate_identity(scenario, seed=1)
    assert [round(g) for g in result.gaps] == [20, 20]


async def test_a_burst_of_simultaneous_requests_still_leaves_one_gap_apart() -> None:
    from evals.ops.measure_queue import burst

    requests = tuple(Request(0.0, operator_name(i % 5)) for i in range(40))
    result = await burst(IdentityScenario("long", 10, 10, None, requests), seed=3)
    assert result.sent == 40
    assert result.gap_violations == 0
    assert result.drain_s == pytest.approx(39 * 10, abs=1e-3)


# -------------------------------------------------------------------------------------- the chain
async def test_the_chain_rings_the_bell_only_for_notices_nobody_acknowledged() -> None:
    report = await measure_notify()
    assert report.bell_rung_after_ack == 0
    assert report.bell_rung_unacked == report.unacked_total > 0
    assert report.texts_with_pii == 0
    assert report.texts_checked > 0
    assert (report.failed, report.pending_at_end, report.skipped) == (0, 0, 0)
    by = {timing.provider: timing for timing in report.by_provider}
    assert by[NotificationProvider.IN_APP].chain_delay_s == (0.0, 0.0)
    assert by[NotificationProvider.PUSH].chain_delay_s == (0.0, 0.0)
    assert by[NotificationProvider.TEAM_GROUP].chain_delay_s == (0.0, 0.0)
    assert by[NotificationProvider.ZALO_BELL].chain_delay_s == (180.0, 180.0), (
        "the bell waits the ack timeout"
    )
    assert by[NotificationProvider.ZALO_BELL].calls == report.unacked_total
    assert all(timing.real_us.n == timing.calls for timing in report.by_provider)


async def test_with_nobody_acknowledging_every_bell_rings_and_with_everybody_none_does() -> None:
    none = await measure_notify(
        NotifyParameters(
            operators=2, notices_per_operator=5, group_notices=1, on_call_notices=1, ack_share=0.0
        )
    )
    everyone = await measure_notify(
        NotifyParameters(
            operators=2, notices_per_operator=5, group_notices=1, on_call_notices=1, ack_share=1.0
        )
    )
    assert none.bell_rung_unacked == 10
    assert everyone.bell_rung_unacked == 0
    assert everyone.bell_rung_after_ack == 0


# ----------------------------------------------------------------------------------- escalation
async def test_a_handoff_nobody_takes_always_reaches_the_on_call_contact_and_one_that_is_taken_never_does() -> (
    None
):
    outcomes = await measure_escalation()
    assert outcomes
    for outcome in outcomes:
        if outcome.case.first_accepts:
            assert outcome.accepted
            assert not outcome.reached_on_call
        else:
            assert outcome.reached_on_call
            assert outcome.outcome == "exhausted_to_oncall"
        assert outcome.model_calls == 0


async def test_the_more_candidates_before_the_contact_the_longer_it_takes_to_reach_the_contact() -> None:
    outcomes = [
        o for o in await measure_escalation() if not o.case.first_accepts and o.case.depth.value == "D2"
    ]
    minutes = [o.minutes_to_on_call for o in sorted(outcomes, key=lambda o: o.case.staff)]
    assert all(m is not None for m in minutes)
    assert minutes == sorted(m for m in minutes if m is not None)
    assert minutes[0] == 0.0, "nobody to ask: the contact is told at once"


# ----------------------------------------------------------------------------------------- report
async def test_the_report_says_not_run_for_the_database_part_and_the_safety_check_passes_without_it() -> None:
    results = OpsResults(
        await measure_queue(),
        await measure_notify(),
        await measure_escalation(),
        None,
        "No throwaway database was given.",
        "",
        "uv run python -m evals.ops.run_eval",
    )
    text = render(results)
    assert "## 4. Claims and replies over a real Postgres" in text
    assert "**Not run.** No throwaway database was given." in text
    assert "## 5. Test suites of this step" in text
    assert safety_failures(results) == []
    assert "Gap violations over all runs: **0**" in text
