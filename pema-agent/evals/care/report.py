# ruff: noqa: E501  - the lines of this file are report text; wrapping them would not make them shorter
"""Renders ``report.md`` from the measurements. New module (not a port).

Rule of the writer: a number is printed only if it was measured in this run; what needs a model that is not
here is printed as ``NOT MEASURED`` with the command that measures it. Failures and misses are listed, not
summarised away.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from evals.care.measure_autonomy import EditDetectorReport, GateSweep, StreamReport, SwitchGrid
from evals.care.measure_depth import DepthReport, FoldDifference, Mode, PerturbationResult
from evals.care.measure_latency import LatencyReport
from evals.care.measure_reminders import ReminderReport
from evals.care.measure_routing import RoutingReport
from evals.care.real_run import RealReport
from evals.care.stats import pct

NOT_MEASURED = "NOT MEASURED"


@dataclass(frozen=True)
class Traffic:
    """A PLACEHOLDER traffic profile (events per patient per month) for the call-count estimate. It is not data
    of the clinic: replace it with the clinic's counts."""

    messages: int = 8
    reminders: int = 3
    tick_drafts: int = 2


@dataclass
class EvalResults:
    generated_at: datetime
    cases: int
    cases_with_marks: int
    cases_without_marks: int
    oracle: DepthReport
    rules_only: DepthReport
    folds_compared: int
    fold_differences: list[FoldDifference]
    perturbations: PerturbationResult
    edits: EditDetectorReport
    gate: GateSweep
    switches: SwitchGrid
    streams: StreamReport | None
    routing: RoutingReport
    reminders: ReminderReport
    latency: LatencyReport
    real: RealReport | None
    commands: list[str]
    environment: str
    traffic: Traffic = Traffic()


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return out


def _ms(value: float) -> str:
    return f"{value:.2f}"


def _depth_section(r: EvalResults) -> list[str]:
    lines = ["## 1. Depth classification", ""]
    lines.append(
        f"{r.cases} labelled cases ({r.cases_with_marks} with Vietnamese diacritics, {r.cases_without_marks} without). "
        "Two runs, both through the real skill `handoff`, the real classifier and the default (temporary) matrix:"
    )
    lines.append("")
    lines.append(
        "- **oracle**: the model answers the label for D2-D4 (and tries to say D1 on red-flag cases). It measures the "
        "rules and the matrix, NOT a model: its accuracy is an upper bound."
    )
    lines.append("- **rules only**: no model at all, what the system does when the model is down.")
    lines.append("")
    for report in (r.oracle, r.rules_only):
        lines.append(f"### {report.mode.value}: accuracy {pct(report.accuracy)} ({report.cases} cases)")
        lines.append("")
        lines.extend(
            _table(
                ["class", "labelled", "predicted", "correct", "recall", "precision"],
                [
                    [
                        c.depth.value,
                        str(c.labelled),
                        str(c.predicted),
                        str(c.correct),
                        pct(c.recall),
                        pct(c.precision),
                    ]
                    for c in report.classes
                ],
            )
        )
        lines.append("")
        lines.append("Confusion (rows label, columns predicted):")
        lines.append("")
        depths = [c.depth for c in report.classes]
        lines.extend(
            _table(
                ["label \\ predicted", *[d.value for d in depths]],
                [
                    [row.value, *[str(report.confusion.get((row, col), 0)) for col in depths]]
                    for row in depths
                ],
            )
        )
        lines.append("")
        lines.append(
            f"- decided by: {', '.join(f'{k} {v}' for k, v in sorted(report.by_source.items()))}; "
            f"cases that needed no model call: {report.cases_without_model}/{report.cases}"
        )
        if report.mode is Mode.ORACLE:
            lines.append(
                f"- accuracy with diacritics {pct(report.accuracy_with_diacritics)} (n={report.n_with_diacritics}), "
                f"without {pct(report.accuracy_without_diacritics)} (n={report.n_without_diacritics})"
            )
        lines.append("")
    o = r.oracle
    lines.append("### D5 (red flag): the safety numbers")
    lines.append("")
    lines.extend(
        _table(
            ["check", "result"],
            [
                ["D5 recall on red-flag cases", f"{o.d5_found}/{o.d5_labelled} = {pct(o.d5_recall)}"],
                ["model calls spent on red-flag cases (adversarial oracle)", str(o.d5_llm_calls)],
                [
                    "red-flag cases reaching urgency `critical`",
                    "all" if o.critical_ok else "NOT ALL",
                ],
                [
                    "recall after 5 rewrites of every red-flag text (upper case, chatter, buried, emoji, spaces)",
                    f"{r.perturbations.checked - len(r.perturbations.missed)}/{r.perturbations.checked}; "
                    f"model calls {r.perturbations.llm_calls}",
                ],
                [
                    "diacritics stripped from every case that has them: action or depth changed",
                    f"{len(r.fold_differences)} of {r.folds_compared} cases",
                ],
                [
                    "D5 false positives (labelled below D5, flagged D5)",
                    str(len(o.d5_false_positives)),
                ],
            ],
        )
    )
    lines.append("")
    for miss in o.d5_false_positives:
        lines.append(
            f"- `{miss.case_id}` labelled {miss.label.value} was flagged D5: over-triage on the safe side "
            "(a doctor looks); the list of red flags is the doctor's to tune."
        )
    for diff in r.fold_differences:
        lines.append(f"- `{diff.case_id}`: {diff.original} as written, {diff.folded} without diacritics")
    lines.append("")
    lines.append("### D1 (administrative) rules")
    lines.append("")
    lines.append(
        f"- labelled D1 and decided by the rules without a model: {o.d1_by_rules}/{o.d1_labelled} "
        f"= {pct(o.d1_by_rules / o.d1_labelled if o.d1_labelled else None)}"
    )
    lines.append(f"- decided D1 by the rules although not labelled D1: {len(o.d1_false_by_rules)}")
    for miss in r.rules_only.depth_misses:
        if miss.label.value == "D1":
            lines.append(
                f"- **miss** `{miss.case_id}`: a D1 case the rules did not place (went to the model, or to the "
                f"D4 fallback when there is none): {miss.source}"
            )
    lines.append("")
    return lines


def _handoff_section(r: EvalResults) -> list[str]:
    lines = ["## 2. Handoff decision (answer or hand off)", ""]
    for report in (r.oracle, r.rules_only):
        h = report.handoff
        lines.append(f"### {report.mode.value}")
        lines.append("")
        lines.extend(
            _table(
                ["metric", "value"],
                [
                    ["positive class", "handoff"],
                    ["TP / FP / FN / TN", f"{h.tp} / {h.fp} / {h.fn} / {h.tn}"],
                    ["precision", pct(h.precision)],
                    ["recall", pct(h.recall)],
                    ["false negatives (should hand off, answered)", str(len(report.false_negatives))],
                    ["false positives (should answer, handed off)", str(len(report.false_positives))],
                    ["required_skill correct", f"{report.skill_correct}/{report.skill_total}"],
                    ["D4 handoffs marked at least `urgent`", "all" if report.urgent_ok else "NOT ALL"],
                ],
            )
        )
        lines.append("")
        if report.false_negatives:
            lines.append("False negatives:")
            lines.extend(
                f"- `{m.case_id}` (label {m.label.value}, predicted {m.predicted.value}, reason {m.reason})"
                for m in report.false_negatives
            )
        else:
            lines.append("False negatives: none.")
        lines.append("")
    lines.append(
        "In the rules-only run every handoff false positive is the safe fallback (`classifier_unavailable`: a person "
        "looks); the oracle run has none because the oracle is always right."
    )
    lines.append("")
    return lines


def _autonomy_section(r: EvalResults) -> list[str]:
    e = r.edits
    lines = ["## 3. Autonomy (L0-L2), trust score, override, switches", ""]
    lines.append(
        "All thresholds are the TEMPORARY defaults (`pending_doctor_approval`): N to L2 = 10, the serious-edit rule, "
        "confidence 0.85."
    )
    lines.append("")
    lines.append("### Serious-edit detector against hand-labelled edit pairs")
    lines.append("")
    lines.append(
        f"{e.pairs} pairs (unchanged / minor / serious); kind accuracy {pct(e.kind_accuracy)}; "
        f"detection of `serious`: precision {pct(e.serious.precision)}, recall {pct(e.serious.recall)} "
        f"(TP {e.serious.tp}, FP {e.serious.fp}, FN {e.serious.fn}, TN {e.serious.tn})."
    )
    for name, label, detected in e.misses:
        lines.append(f"- **miss** `{name}`: labelled {label}, detected {detected}")
    lines.append("")
    g = r.gate
    lines.append("### Auto-send gate, exhaustive sweep")
    lines.append("")
    lines.append(
        f"{g.combinations} combinations (action type x level x depth x red flag x verified x opt-out x citations x "
        f"confidence x scheduled x template): the gate allowed {g.allowed}; "
        f"**hard-rule violations {len(g.violations)}**; abilities the plan grants that the gate refused "
        f"{len(g.unexpected_refusals)}."
    )
    for item in (*g.violations, *g.unexpected_refusals):
        lines.append(f"- {item}")
    sw = r.switches
    lines.append("")
    lines.append(
        f"Override / pause / kill-switch grid: {sw.combinations} combinations, violations {len(sw.violations)}."
    )
    for item in sw.violations:
        lines.append(f"- {item}")
    lines.append("")
    s = r.streams
    if s is None:
        lines.append(
            f"### Review streams: {NOT_MEASURED} here (no throwaway Postgres: set `PEMA_EVAL_CARE_DATABASE_URL`)."
        )
        lines.append("")
        return lines
    lines.append("### Review streams (Postgres)")
    lines.append("")
    lines.extend(
        _table(
            ["scenario", "result"],
            [
                [
                    f"promotion after N approved-unchanged drafts, N={row.n}",
                    f"promoted at draft {row.approvals_needed}; promoted early: {'YES' if row.promoted_early else 'no'}",
                ]
                for row in s.promotion
            ]
            + [
                ["20 minor edits fed", f"{s.minor_edits_counted} counted toward promotion"],
                ["10 rejections fed", f"{s.rejected_counted} counted toward promotion"],
                [
                    "one serious edit after promotion",
                    f"demoted to L0: {s.serious_demoted}; manager alerts: {s.serious_alerts}; "
                    f"score after: {s.scores_after_demotion}; drafts needed to re-promote (N=5): {s.repromotion_needed}",
                ],
                [
                    "medical judgement approved unchanged x8",
                    f"score {s.medical_score}; ever above L0: {s.medical_promoted}; "
                    f"a serious edit of it still demotes: {s.medical_serious_demoted}",
                ],
                ["override L0 for 7 days", f"day 3: {s.override_day3}; day 8: {s.override_day8}"],
                [
                    f"seeded random stream of {s.random_steps} reviews (seed {s.random_seed}) vs an independent reference model",
                    f"{s.random_steps - len(s.random_mismatches)}/{s.random_steps} steps agree; "
                    f"{s.random_promotions} promotions, {s.random_demotions} demotions",
                ],
            ],
        )
    )
    lines.extend(f"- mismatch {m}" for m in s.random_mismatches[:10])
    lines.append("")
    return lines


def _routing_section(r: EvalResults) -> list[str]:
    x = r.routing
    lines = ["## 4. Routing and SLA (fake clock)", ""]
    lines.append(
        f"{x.scenarios} scenarios: staff 0..9, with and without an owner, depth D1-D5, in hours (Mon 10:00) and out of "
        "hours (Mon 22:00), staff who all decline, all stay silent, or the first accepts."
    )
    lines.append("")
    lines.extend(
        _table(
            ["invariant", "result"],
            [
                ["chain length 1..5 and ends with exactly one on-call entry", f"{x.chain_ok}/{x.scenarios}"],
                [
                    "when nobody accepts, the chain ends at the on-call contact",
                    f"{x.ends_at_on_call}/{x.expected_to_end_at_on_call}",
                ],
                [
                    "on-call contact notified exactly once",
                    f"{x.on_call_exactly_once}/{x.expected_to_end_at_on_call}",
                ],
                [
                    "nobody asked after the on-call contact",
                    f"{x.nobody_after_on_call}/{x.expected_to_end_at_on_call}",
                ],
                [
                    "SLA deadline as specified (5 / 30 min in hours, next shift out of hours)",
                    f"{x.sla_ok}/{x.sla_checked}",
                ],
                [
                    "out of hours, D3 or deeper goes straight to the on-call contact",
                    f"{x.direct_to_on_call_out_of_hours}/{x.direct_expected}",
                ],
                [
                    "first candidate accepts: conversation goes to staff",
                    f"{x.accepted_ok}/{x.accepted_expected}",
                ],
                ["turns that needed no model call (reply or depth)", f"{x.no_model_calls}/{x.scenarios}"],
            ],
        )
    )
    lines.append("")
    lines.append(
        "Time until the on-call contact is asked when every staff member stays silent (fake clock, minutes):"
    )
    lines.append("")
    lines.extend(
        _table(
            ["clock", "urgency", "staff asked first", "minutes"],
            [[c, u, str(n), f"{m:g}"] for c, u, n, m in x.time_to_on_call],
        )
    )
    lines.extend(f"- problem: {p}" for p in x.problems)
    lines.append("")
    return lines


def _latency_section(r: EvalResults) -> list[str]:
    x = r.latency
    lines = ["## 5. Latency and the daily tick (orchestration only)", ""]
    lines.append(
        "**Every model here is a fake that answers instantly.** These are the milliseconds package M itself adds "
        f"(queue, state machine, skill, rules, routing, specialist loop), {x.samples} timed runs per row after "
        f"{10} warm-up runs, in-memory stores, one process. The wall time a patient waits is these plus the model "
        "latency, which is "
        f"{NOT_MEASURED} (needs the GPU run, section 9)."
    )
    lines.append("")
    lines.extend(
        _table(
            [
                "patient message to reply draft",
                "p50 ms",
                "p95 ms",
                "max ms",
                "depth-model calls",
                "reply-model calls",
                "specialist model steps",
                "outcome",
            ],
            [
                [
                    c.name,
                    _ms(c.latency.p50),
                    _ms(c.latency.p95),
                    _ms(c.latency.max),
                    f"{c.depth_model_calls:g}",
                    f"{c.reply_model_calls:g}",
                    f"{c.specialist_model_steps:g}",
                    c.outcome,
                ]
                for c in x.classes
            ],
        )
    )
    lines.append("")
    lines.append(
        f"Daily tick over {x.ticks[0].patients} fake patients (the share of patients whose rules say a text must be drafted is varied):"
    )
    lines.append("")
    lines.extend(
        _table(
            [
                "patients needing a draft",
                "batches",
                "tick wall ms",
                "drafts queued",
                "drain wall ms (fake reply model)",
                "reply-model calls",
                "depth-model calls",
            ],
            [
                [
                    pct(t.draft_share),
                    str(t.batches),
                    _ms(t.tick_ms),
                    str(t.drafts),
                    _ms(t.drain_ms),
                    str(t.harness_calls),
                    str(t.depth_model_calls),
                ]
                for t in x.ticks
            ],
        )
    )
    lines.append("")
    lines.append(
        "The tick itself makes no model call: the number of calls equals the number of patients that need a draft, "
        "and the depth classifier is never used for a tick draft. Rules run once per batch of 100, not per patient."
    )
    lines.append("")
    return lines


def _cost_section(r: EvalResults) -> list[str]:
    o, t = r.oracle, r.traffic
    n = max(o.cases, 1)
    depth_rate = o.llm_calls_total / n
    reply_rate = (o.handoff.tn + o.handoff.fn) / n
    depth_calls = t.messages * depth_rate
    reply_calls = t.messages * reply_rate + t.reminders + t.tick_drafts
    lines = ["## 6. Cost per patient per month", ""]
    lines.append(
        "Tokens per call need a real model: **tokens per patient per month: "
        f"{NOT_MEASURED}**. What is measured is the number of model calls the orchestration makes, and the size of "
        "the classifier prompt."
    )
    lines.append("")
    lines.append(
        f"- classifier prompt: {r.latency.classifier_prompt_chars_mean:.0f} characters (instruction + JSON "
        f"schema + the message), measured; characters, not tokens"
    )
    lines.append(
        f"- over the labelled cases the oracle run spent {o.llm_calls_total} depth-model calls on {o.cases} messages "
        f"({depth_rate:.2f} per message: D1 by rules and D5 red flags need none); {pct(reply_rate)} of the messages "
        "reach the reply model (the others are handed to a person before it)"
    )
    lines.append("- a reminder or a tick draft is one reply-model call and no depth call (section 5)")
    lines.append(
        f"- with the PLACEHOLDER traffic of {t.messages} patient messages, {t.reminders} reminders and "
        f"{t.tick_drafts} tick drafts per patient per month (not clinic data): about {depth_calls:.1f} depth-model calls "
        f"and {reply_calls:.1f} reply-model calls per patient per month, before any specialist step"
    )
    lines.append(
        "- tokens per patient per month = depth calls x tokens per depth call + reply calls x tokens per reply call "
        "+ specialist steps x tokens per step; the first and the third come out of `real_run`, the second needs the "
        "wiring package's engine adapter"
    )
    lines.append("")
    return lines


def _reminders_section(r: EvalResults) -> list[str]:
    x = r.reminders
    lines = ["## 7. Reminder pause and reconcile", ""]
    lines.extend(
        _table(
            ["scenario group", "passed / total"],
            [[t.name, f"{t.passed}/{t.total}"] for t in x.tallies],
        )
    )
    lines.append("")
    lines.append(
        f"{x.scenarios} scenarios. Messages that reached the patient while a person had the conversation: "
        f"**{x.sent_to_patient_while_staff}**. Model calls while a person had the conversation: "
        f"**{x.model_calls_while_staff}**. Outcomes in the matrix: {x.resumed} resumed, "
        f"{x.dropped_past_meaning} dropped as past their meaning, {x.dropped_superseded} dropped as superseded in the "
        f"series scenarios, hand-sent not resumed {x.sent_by_hand_not_resumed}/1. Resumed texts that carry the "
        f'"(nhắc trễ, lịch gốc HH:MM)" label: {x.late_label_ok}/{x.late_label_checked} (the rest were deferred to '
        "the send window and have no text yet, or are birthday drafts)."
    )
    lines.append("The windows (D+1 48 h, D+3 120 h, ...) are the temporary defaults, awaiting the doctor.")
    lines.extend(f"- failure: {f}" for f in x.failures)
    lines.append("")
    return lines


def _real_section(r: EvalResults) -> list[str]:
    lines = ["## 8. Real model run", ""]
    real = r.real
    if real is None:
        lines.append(
            f"{NOT_MEASURED}. This run had no model: the Windows development box has no Ollama and no GPU and the "
            "local model is switched off in this repository (TẠM TẮT LLM LOCAL). Nothing below is invented."
        )
        lines.append("")
        return lines
    d = real.depth
    lines.append(
        f"Model: `{real.model_label}`. Cases {d.cases}, depth accuracy {pct(d.accuracy)}, handoff precision "
        f"{pct(d.handoff.precision)}, recall {pct(d.handoff.recall)}, false negatives {len(d.false_negatives)}, "
        f"D5 recall {pct(d.d5_recall)} with {d.d5_llm_calls} model calls on red-flag cases, replies that were "
        f"not valid JSON (fallback): {real.fallbacks}."
    )
    lines.append("")
    c = real.classifier
    lines.append(
        f"Classifier call: {c.calls} calls, p50 {_ms(c.latency.p50)} ms, p95 {_ms(c.latency.p95)} ms, tokens per call "
        f"input {c.input_tokens_mean}, output {c.output_tokens_mean}, total {c.total_tokens_mean} "
        f"({c.unreported} calls without usage)."
    )
    for row in real.specialists:
        lines.append(
            f"- {row.specialist}: {row.delegations} delegations, p50 {_ms(row.latency.p50)} ms, p95 "
            f"{_ms(row.latency.p95)} ms, needs_human {row.needs_human}, tokens per model call "
            f"{row.model.total_tokens_mean}"
        )
    lines.append("")
    return lines


def _commands_section(r: EvalResults) -> list[str]:
    lines = ["## 9. What needs the Ubuntu + RTX 3060 + Qwen3-8B run", ""]
    lines.append("Not measured on this box, with the command that measures each (from `pema-agent/backend`):")
    lines.append("")
    lines.extend(
        _table(
            ["number", "needs", "measured by"],
            [
                [
                    "depth accuracy of D2-D4 with the real classifier, handoff precision/recall and false negatives with it",
                    "the model",
                    "`real_run`, section 8",
                ],
                ["share of classifier replies that are not valid JSON", "the model", "`real_run`"],
                [
                    "p50/p95 of one classifier call, of a specialist delegation",
                    "the model on the GPU",
                    "`real_run`",
                ],
                [
                    "patient message to reply draft, with and without specialists",
                    "the model + the engine adapter (wiring package)",
                    "not wired yet",
                ],
                [
                    "tokens per patient per month",
                    "the model's usage + the clinic's traffic",
                    "`real_run` x section 6 formula",
                ],
                [
                    "share of drafts approved unchanged, by type",
                    "real drafts reviewed by staff",
                    "pilot data in `agent.review_items`",
                ],
            ],
        )
    )
    lines.append("")
    lines.append("```bash")
    lines.append("cd pema-agent/backend")
    lines.append("ollama pull qwen3:8b")
    lines.append(
        "export LLM_PROVIDER=openai-compatible LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen3:8b LLM_API_KEY=ollama"
    )
    lines.append(
        "export PEMA_EVAL_CARE_DATABASE_URL=postgresql+psycopg://postgres:<pw>@127.0.0.1:55432/pema   # THROWAWAY database"
    )
    lines.append(
        "PYTHONPATH=.. uv run python -m evals.care.run_eval --real --out ../evals/care/report-real.md"
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "Read the first line it prints (`Model: ...`) before the numbers. Run it three times before judging a "
        "single red case: a small local model varies between runs."
    )
    lines.append("")
    return lines


def _findings_section(r: EvalResults) -> list[str]:
    lines = ["## Findings (failures and misses, plainly)", ""]
    found: list[str] = []
    for miss in r.rules_only.depth_misses:
        if miss.label.value == "D1":
            found.append(
                f"D1 rule gap: case `{miss.case_id}` is administrative but no D1 rule matches it, so without a model "
                "it falls to the D4 fallback (a person answers a question about opening hours). Fix: add the pattern "
                "to `pema.care.depth` (owner: M2b), the cases stay as the regression."
            )
    for name, label, detected in r.edits.misses:
        found.append(
            f"Serious-edit detector miss: `{name}` (labelled {label}, detected {detected}). A missed serious edit "
            "keeps the agent at its level (`pema.care.trust`, owner: M3: the negation list has no plain "
            '"không" + verb).'
        )
    for miss in r.oracle.d5_false_positives:
        found.append(
            f"Red-flag over-triage: `{miss.case_id}` ({miss.label.value} by label) goes to a doctor as D5: safe side, "
            "but it costs a doctor a glance; the doctor decides whether pustular acne should be on the list."
        )
    for miss in r.oracle.false_negatives:
        found.append(f"Handoff false negative with the oracle: `{miss.case_id}`.")
    for item in r.gate.violations:
        found.append(f"Auto-send gate violation: {item}")
    for problem in r.routing.problems:
        found.append(f"Routing: {problem}")
    for failure in r.reminders.failures:
        found.append(f"Reminders: {failure}")
    if r.streams is not None:
        found.extend(f"Stream mismatch: {m}" for m in r.streams.random_mismatches[:5])
    if not found:
        lines.append("None.")
    lines.extend(f"- {item}" for item in found)
    lines.append("")
    return lines


def render(r: EvalResults) -> str:
    out: list[str] = []
    out.append("# Care agent evaluation: package M, step M6")
    out.append("")
    out.append(
        f"Generated {r.generated_at.strftime('%Y-%m-%d %H:%M')} UTC by `evals.care.run_eval`. {r.environment}"
    )
    out.append("")
    out.append("Commands used for this report:")
    out.append("")
    out.append("```bash")
    out.extend(r.commands)
    out.append("```")
    out.append("")
    out.append("## 0. Read this first")
    out.append("")
    out.append(
        "Everything here ran **without a model**. The labelled cases are synthetic and labelled from the default matrix "
        "of PLAN-AI01-M section 6 (temporary, awaiting the doctor), not by a doctor. A model-dependent number appears "
        f"only if section 8 says it was measured; otherwise it is `{NOT_MEASURED}` and section 9 gives the command."
    )
    out.append("")
    out.append(
        "No prompt or configuration was changed to improve a number: the defaults of `HandoffConfig`, "
        "`AutonomySettings`, `RoutingConfig` and the classifier prompt are exactly those of the repository."
    )
    out.append("")
    out.extend(_findings_section(r))
    out.extend(_depth_section(r))
    out.extend(_handoff_section(r))
    out.extend(_autonomy_section(r))
    out.extend(_routing_section(r))
    out.extend(_latency_section(r))
    out.extend(_cost_section(r))
    out.extend(_reminders_section(r))
    out.extend(_real_section(r))
    out.extend(_commands_section(r))
    return "\n".join(out).rstrip() + "\n"


__all__ = ["EvalResults", "Mode", "Traffic", "render"]
