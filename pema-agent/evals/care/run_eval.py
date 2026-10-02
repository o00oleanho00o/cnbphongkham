"""Run the care eval and write ``report.md``. New module (not a port).

From ``pema-agent/backend``::

    PYTHONPATH=.. uv run python -m evals.care.run_eval           # everything that needs no model
    PYTHONPATH=.. PEMA_EVAL_CARE_DATABASE_URL=postgresql+psycopg://... uv run python -m evals.care.run_eval
    PYTHONPATH=.. uv run python -m evals.care.run_eval --real --out ../evals/care/report-real.md  # GPU box

The review streams of the autonomy section need a THROWAWAY Postgres (it is dropped and re-created);
without ``PEMA_EVAL_CARE_DATABASE_URL`` (or ``PEMA_TEST_DATABASE_URL``) that part is reported as not measured.
``--real`` additionally runs ``real_run`` against the configured model (the same ``LLM_*`` settings as
``evals/run_eval.py``). Exit code 1 when a safety invariant fails (a red flag missed or a model called
for it, a
hard rule of the auto-send gate broken, a routing chain that does not end at the on-call contact, a reminder
sent to a patient while a person had the conversation); a defect of a rule list is reported, not an exit code.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evals.care.cases import load_cases
from evals.care.db_setup import database_url_from_env, seeded_database
from evals.care.measure_autonomy import (
    StreamReport,
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
from evals.care.measure_latency import SAMPLES, measure_latency
from evals.care.measure_reminders import measure_reminders
from evals.care.measure_routing import measure_routing
from evals.care.real_run import ModelFactory, RealReport, run_real
from evals.care.report import EvalResults, render
from pema.config.runtime_settings_kv import InMemoryRuntimeSettingsKv, install_runtime_settings_kv
from pema.core.event_loop import ensure_selector_event_loop_policy

DEFAULT_OUT = Path(__file__).with_name("report.md")


def safety_failures(results: EvalResults) -> list[str]:
    o = results.oracle
    failures: list[str] = []
    if o.d5_found != o.d5_labelled:
        failures.append("a red flag was missed")
    if o.d5_llm_calls or results.perturbations.llm_calls:
        failures.append("a model was called on a red-flag case")
    if results.perturbations.missed:
        failures.append("a rewritten red flag was missed")
    if results.gate.violations or results.switches.violations:
        failures.append("a hard rule of the auto-send gate was broken")
    r = results.routing
    if r.problems or r.ends_at_on_call != r.expected_to_end_at_on_call:
        failures.append("a routing chain did not end at the on-call contact")
    if results.reminders.sent_to_patient_while_staff or results.reminders.failures:
        failures.append("a reminder scenario failed")
    if results.streams is not None and results.streams.random_mismatches:
        failures.append("the trust score disagrees with the reference model")
    return failures


async def _real_factory() -> tuple[ModelFactory, str, object] | str:
    """The configured model, or the message to print when none is configured."""
    from evals.eval_env import dung_eval_env
    from pema.agent.llm_provider import resolve_language_model

    env = await dung_eval_env()
    if not env.ok or env.llm is None:
        return env.loi
    label = f"{env.llm.model} ({env.llm.provider})"
    return (lambda purpose: resolve_language_model(None, None)), label, env.restore


async def gather(*, real: bool, runs: int, db_url: str | None, commands: Sequence[str]) -> EvalResults | str:
    cases = load_cases()
    oracle = summarize(Mode.ORACLE, await run_cases(cases, Mode.ORACLE))
    rules_only = summarize(Mode.RULES_ONLY, await run_cases(cases, Mode.RULES_ONLY))
    compared, differences = await fold_variant_differences(cases)
    perturbations = await redflag_perturbations(cases)

    streams: StreamReport | None = None
    if db_url is not None:
        install_runtime_settings_kv(InMemoryRuntimeSettingsKv())
        async with seeded_database(db_url) as (db, world):
            streams = await simulate_streams(db, list(world.patients.values()))

    real_report: RealReport | None = None
    if real:
        built = await _real_factory()
        if isinstance(built, str):
            return built
        factory, label, restore = built
        sys.stdout.write(f"Model: {label}\n")
        try:
            real_report = await run_real(cases, factory, model_label=label)
        finally:
            if callable(restore):
                restore()

    sample_texts = [" ".join(case.texts) for case in cases if case.texts]
    return EvalResults(
        generated_at=datetime.now(UTC),
        cases=len(cases),
        cases_with_marks=sum(1 for c in cases if c.has_diacritics),
        cases_without_marks=sum(1 for c in cases if not c.has_diacritics),
        oracle=oracle,
        rules_only=rules_only,
        folds_compared=compared,
        fold_differences=differences,
        perturbations=perturbations,
        edits=edit_detector_report(),
        gate=gate_sweep(),
        switches=switch_grid(),
        streams=streams,
        routing=await measure_routing(),
        reminders=await measure_reminders(),
        latency=await measure_latency(sample_texts, runs=runs),
        real=real_report,
        commands=list(commands),
        environment=(
            f"Python {platform.python_version()} on {platform.system()}; "
            f"model: {'real (section 8)' if real else 'none'}; "
            f"Postgres: {'throwaway database' if db_url else 'none'}."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Care agent evaluation (package M, step M6)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the report")
    parser.add_argument(
        "--real", action="store_true", help="also run the measurements that need a real model"
    )
    parser.add_argument("--runs", type=int, default=SAMPLES, help="timed runs per latency row")
    parser.add_argument("--no-db", action="store_true", help="skip the Postgres-backed review streams")
    args = parser.parse_args(argv)

    db_url = None if args.no_db else database_url_from_env()
    commands = [
        "cd pema-agent/backend",
        "PYTHONPATH=.. PEMA_EVAL_CARE_DATABASE_URL=<throwaway postgres> uv run python -m evals.care.run_eval"
        + (" --real" if args.real else "")
        + (f" --runs {args.runs}" if args.runs != SAMPLES else "")
        + (" --no-db" if args.no_db else ""),
    ]
    ensure_selector_event_loop_policy()
    outcome = asyncio.run(gather(real=args.real, runs=args.runs, db_url=db_url, commands=commands))
    if isinstance(outcome, str):
        sys.stdout.write(f"{outcome}\n")
        return 1
    args.out.write_text(render(outcome), encoding="utf-8")
    failures = safety_failures(outcome)
    sys.stdout.write(f"report written to {args.out}\n")
    for failure in failures:
        sys.stdout.write(f"SAFETY FAILURE: {failure}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
