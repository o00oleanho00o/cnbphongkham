"""Tests of the care eval itself (package M, step M6). New tests (no zalo-agent original).

They check that the cases are well formed and that the measurements measure what the report says. No model
runs here: the "real" path is exercised with a scripted model, which proves the plumbing and nothing about a
real model. The Postgres-backed streams are skipped without ``PEMA_TEST_DATABASE_URL``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import pytest

from evals.care.cases import CaseError, case_from_item, load_cases
from evals.care.measure_autonomy import (
    EDIT_PAIRS,
    ReferenceModel,
    edit_detector_report,
    gate_sweep,
    simulate_streams,
    switch_grid,
)
from evals.care.measure_depth import (
    Mode,
    fold_variant_differences,
    redflag_perturbations,
    run_cases,
    summarize,
)
from evals.care.measure_reminders import measure_reminders
from evals.care.measure_routing import measure_routing
from evals.care.real_run import CallRecord, call_stats, run_real
from evals.care.report import render
from evals.care.run_eval import gather, safety_failures
from evals.care.stats import Confusion, percentile, ratio
from evals.care.yaml_subset import YamlSubsetError, parse_cases
from pema.agent.model_types import ChatModel, ModelCompletion, ModelUsage
from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool, tra_loi
from pema.care.handoff_types import Depth
from pema.care.trust import EditKind
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.runtime_settings_kv import (
    InMemoryRuntimeSettingsKv,
    install_runtime_settings_kv,
    reset_runtime_settings_kv,
)
from pema.core.db import ClinicDatabase
from pema.policy.redflags import REQUIRED_CATEGORIES, detect_red_flags_in_batch


@pytest.fixture(autouse=True)
def kv() -> Iterator[None]:
    install_runtime_settings_kv(InMemoryRuntimeSettingsKv())
    yield
    reset_runtime_settings_kv()


# ------------------------------------------------------------------------------------- the file format
def test_the_yaml_subset_reads_items_lists_and_scalars() -> None:
    items = parse_cases(
        '# c\n- id: a\n  text: "xin \\"chào\\""\n  n: 3\n  f: 0.5\n  ok: true\n  none: null\n'
        '  words: ["x", "y"]\n  empty: []\n- id: b\n  depth: D2\n'
    )
    assert items == [
        {
            "id": "a",
            "text": 'xin "chào"',
            "n": 3,
            "f": 0.5,
            "ok": True,
            "none": None,
            "words": ["x", "y"],
            "empty": [],
        },
        {"id": "b", "depth": "D2"},
    ]


@pytest.mark.parametrize(
    "text",
    ["id: a\n", "- id a\n", "- id: a\n  id: b\n", "- id: {a: 1}\n", '- id: "open\n', "- id:\n", "- id: [a\n"],
)
def test_the_yaml_subset_refuses_what_it_does_not_read(text: str) -> None:
    with pytest.raises(YamlSubsetError):
        parse_cases(text)


# ------------------------------------------------------------------------------------------- the cases
def test_there_are_at_least_sixty_cases_with_unique_ids_and_every_depth() -> None:
    cases = load_cases()
    assert len(cases) >= 60
    assert len({c.id for c in cases}) == len(cases)
    assert {c.depth for c in cases} == set(Depth)
    for depth in Depth:
        assert sum(1 for c in cases if c.depth is depth) >= 10


def test_the_cases_are_written_with_and_without_diacritics() -> None:
    cases = load_cases()
    assert sum(1 for c in cases if c.has_diacritics) >= 20
    assert sum(1 for c in cases if not c.has_diacritics) >= 10


def test_the_red_flag_cases_cover_every_category_of_the_list() -> None:
    found: set[str] = set()
    for case in load_cases():
        if case.depth is Depth.D5:
            found.update(detect_red_flags_in_batch(case.texts).flags)
    assert set(REQUIRED_CATEGORIES) <= found
    assert {"severe_allergy", "vascular_vision"} <= found


def test_the_cases_cover_the_signals_of_the_matrix() -> None:
    cases = load_cases()
    assert any(c.vip for c in cases)
    assert any(not c.verified for c in cases)
    assert any(c.hour >= 21 or c.hour <= 5 for c in cases)
    assert any(c.procedure_hours_ago is not None for c in cases)
    assert any(c.repeat_count >= 2 for c in cases)
    assert any(c.complex_history for c in cases)
    assert any(c.past_complaint for c in cases)
    assert any(c.pending_doctor_work for c in cases)
    assert any(c.conf < 0.6 for c in cases)


def test_a_case_with_an_unknown_key_or_a_bad_value_is_refused() -> None:
    base = {"id": "x", "text": "a", "depth": "D2", "action": "answer"}
    for bad in ({"colour": "red"}, {"depth": "D9"}, {"hour": 30}, {"conf": 1.5}):
        with pytest.raises(CaseError):
            case_from_item({**base, **bad})


# ------------------------------------------------------------------------------------------ depth
async def test_d5_recall_is_total_and_no_model_is_called_on_a_red_flag() -> None:
    report = summarize(Mode.ORACLE, await run_cases(load_cases(), Mode.ORACLE))
    assert report.d5_labelled >= 15
    assert report.d5_found == report.d5_labelled
    assert report.d5_llm_calls == 0
    assert report.critical_ok


async def test_a_red_flag_survives_every_rewrite_and_never_reaches_the_model() -> None:
    result = await redflag_perturbations(load_cases())
    assert result.checked >= 75
    assert result.missed == []
    assert result.llm_calls == 0


async def test_stripping_the_diacritics_changes_no_decision() -> None:
    compared, differences = await fold_variant_differences(load_cases())
    assert compared >= 20
    assert differences == []


async def test_without_a_model_nothing_that_needs_a_person_is_answered() -> None:
    report = summarize(Mode.RULES_ONLY, await run_cases(load_cases(), Mode.RULES_ONLY))
    assert report.false_negatives == []
    assert report.cases_without_model == report.cases
    assert report.d5_found == report.d5_labelled


async def test_the_oracle_run_agrees_with_the_labels_except_over_triage() -> None:
    report = summarize(Mode.ORACLE, await run_cases(load_cases(), Mode.ORACLE))
    assert report.false_negatives == []
    assert [m.case_id for m in report.depth_misses] == [
        "d4-10"
    ]  # pustular acne: the red-flag list over-triages
    assert report.handoff.recall == 1.0


async def test_known_gap_the_d1_rules_miss_opening_hours_in_the_reverse_word_order() -> None:
    """Open item for package M2b: "mở cửa mấy giờ" is not matched by the D1 rules (only "mấy giờ mở cửa"). When
    the pattern is added this test must be changed to expect zero misses."""
    report = summarize(Mode.RULES_ONLY, await run_cases(load_cases(), Mode.RULES_ONLY))
    assert [m.case_id for m in report.depth_misses if m.label is Depth.D1] == ["d1-13"]


# --------------------------------------------------------------------------------------- statistics
def test_percentile_interpolates_and_handles_no_data() -> None:
    assert percentile([], 95) == 0.0
    assert percentile([4.0], 50) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0
    assert ratio(0, 0) is None
    assert Confusion().precision is None


# ------------------------------------------------------------------------------------------ autonomy
def test_the_auto_send_gate_breaks_no_hard_rule_in_any_combination() -> None:
    sweep = gate_sweep()
    assert sweep.combinations > 10_000
    assert sweep.violations == []
    assert sweep.unexpected_refusals == []


def test_no_override_pause_or_switch_raises_a_level() -> None:
    assert switch_grid().violations == []


def test_the_edit_detector_never_calls_a_wording_change_serious() -> None:
    report = edit_detector_report()
    assert report.pairs == len(EDIT_PAIRS) >= 20
    assert report.serious.fp == 0
    assert all(
        label != EditKind.UNCHANGED.value or detected == "unchanged" for _, label, detected in report.misses
    )


def test_known_misses_of_the_serious_edit_detector_are_the_two_negation_cases() -> None:
    """Open item for package M3: the negation list of ``SeriousEditRule`` has no plain "không" + verb. When it
    is fixed this test must be changed to ``== set()``."""
    names = {name for name, _, _ in edit_detector_report().misses}
    assert names == {"prohibition removed", "a 'do not' reversed into 'do'"}


def test_the_reference_model_follows_the_plan() -> None:
    ref = ReferenceModel(n=2)
    for step in ("unchanged", "minor", "rejected", "unchanged"):
        ref.apply(step)
    assert (ref.level.value, ref.promotions) == ("L2", 1)
    ref.apply("serious")
    assert (ref.level.value, ref.score, ref.demotions) == ("L0", 0, 1)


@pytest.mark.db
async def test_the_review_streams_promote_demote_and_match_the_reference(
    db: ClinicDatabase, world: SeedResult
) -> None:
    report = await simulate_streams(db, list(world.patients.values()))
    assert [(row.n, row.approvals_needed, row.promoted_early) for row in report.promotion] == [
        (3, 3, False),
        (5, 5, False),
        (10, 10, False),
    ]
    assert (report.minor_edits_counted, report.rejected_counted) == (0, 0)
    assert report.serious_demoted
    assert report.serious_alerts == 1
    assert (report.scores_after_demotion, report.repromotion_needed) == (0, 5)
    assert (report.medical_score, report.medical_promoted, report.medical_serious_demoted) == (0, False, True)
    assert (report.override_day3, report.override_day8) == ("L0", "L2")
    assert report.random_mismatches == []


# -------------------------------------------------------------------------- routing and reminders
async def test_routing_invariants_hold_in_every_scenario() -> None:
    report = await measure_routing()
    assert report.scenarios >= 300
    assert report.problems == []
    assert report.ends_at_on_call == report.expected_to_end_at_on_call > 0
    assert report.on_call_exactly_once == report.expected_to_end_at_on_call
    assert report.sla_ok == report.sla_checked
    assert report.no_model_calls == report.scenarios
    assert 30.0 in [
        m for _, urgency, asked, m in report.time_to_on_call if urgency == "normal" and asked == 1
    ]


async def test_reminders_are_never_sent_while_a_person_has_the_conversation() -> None:
    report = await measure_reminders()
    assert report.failures == []
    assert report.sent_to_patient_while_staff == 0
    assert report.model_calls_while_staff == 0
    assert report.scenarios >= 90
    assert report.late_label_ok == report.late_label_checked > 0


# ---------------------------------------------------------------------------- the report end to end
async def test_a_run_without_a_model_renders_a_report_that_says_what_it_did_not_measure() -> None:
    results = await gather(real=False, runs=5, db_url=None, commands=["x"])
    assert not isinstance(results, str)
    assert safety_failures(results) == []
    text = render(results)
    for heading in (
        "## Findings",
        "## 1. Depth classification",
        "## 2. Handoff decision",
        "## 3. Autonomy",
        "## 4. Routing and SLA",
        "## 5. Latency and the daily tick",
        "## 6. Cost per patient per month",
        "## 7. Reminder pause and reconcile",
        "## 8. Real model run",
        "## 9. What needs the Ubuntu + RTX 3060 + Qwen3-8B run",
    ):
        assert heading in text
    assert "tokens per patient per month: NOT MEASURED" in text
    assert "D5 recall on red-flag cases | 19/19" in text


async def test_a_safety_failure_is_reported() -> None:
    results = await gather(real=False, runs=2, db_url=None, commands=[])
    assert not isinstance(results, str)
    results.oracle.d5_llm_calls = 1
    assert "a model was called on a red-flag case" in safety_failures(results)


# ----------------------------------------------------------------------------------- the real path
def _reply(text: str) -> Callable[[], ModelCompletion | Exception]:
    return lambda: tra_loi(text, ModelUsage(100, 20, 120))


def _specialist_model(tool: str, args: dict[str, object]) -> ScriptedModel:
    steps: list[Callable[[], ModelCompletion | Exception]] = []
    for index in range(4):
        steps.append(lambda index=index: goi_tool(tool, args, call_id=f"t-{tool}-{index}"))
        steps.append(
            lambda index=index: goi_tool(
                "submit_result", {"summary": "xong", "confidence": 0.8}, call_id=f"s-{tool}-{index}"
            )
        )
    return ScriptedModel(steps)


def _models(classifier_reply: str) -> dict[str, ChatModel]:
    return {
        "classifier": ScriptedModel([_reply(classifier_reply)]),
        "knowledge": _specialist_model("kb_search", {"question": "sau peel"}),
        "scheduler": _specialist_model(
            "appointment.search_slots", {"from_date": "2026-10-07", "to_date": "2026-10-14"}
        ),
    }


async def test_the_real_path_runs_on_a_scripted_model_and_counts_calls_and_tokens() -> None:
    models = _models(json.dumps({"depth": "D2", "confidence": 0.9}))
    cases = load_cases()
    report = await run_real(cases, lambda purpose: models[purpose], model_label="scripted", delegation_runs=2)
    assert report.depth.cases == len(cases)
    assert report.depth.d5_llm_calls == 0  # red flags never reach the model, real or scripted
    assert report.classifier.calls == report.depth.llm_calls_total > 0
    assert report.classifier.total_tokens_mean == 120
    assert report.fallbacks == 0
    assert [row.specialist for row in report.specialists] == ["care-knowledge", "care-scheduler"]
    assert all(row.delegations == 2 for row in report.specialists)


async def test_a_real_run_with_an_unusable_model_falls_back_to_a_person() -> None:
    models = _models("not json at all")
    report = await run_real(
        load_cases(), lambda purpose: models[purpose], model_label="scripted", delegation_runs=1
    )
    assert report.fallbacks > 0
    assert report.depth.false_negatives == []


def test_call_stats_leaves_calls_without_usage_out_of_the_token_means() -> None:
    stats = call_stats([CallRecord(1_000_000, ModelUsage(10, 5, 15)), CallRecord(3_000_000, ModelUsage())])
    assert (stats.calls, stats.unreported, stats.total_tokens_mean) == (2, 1, 15)
    assert stats.latency.p50 == 2.0
