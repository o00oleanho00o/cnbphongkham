# M6 — Evaluation and real-number report

## Goal
Measure package M on real runs (Ollama, RTX 3060, Qwen3-8B) with labelled synthetic cases, and report numbers, not impressions.

## Read first
1. `PLAN-AI01-M.md` §13 (M6), §14.
2. `pema-agent/evals/` conventions from the ported zalo-agent evals.
3. Red-flag list from P; depth matrix defaults from M2b.

## Ingredients
- `pema-agent/evals/care/cases.yaml`: ≥ 60 synthetic cases labelled with depth D1–D5, expected action (`answer|handoff`), expected `required_skill`, VIP/unverified flags, time of day. Written in Vietnamese, with and without diacritics. No real names/numbers.
- `pema-agent/evals/care/run_eval.py`: runs cases through `handoff_skill` + `depth`, and through full turns for a subset.
- `pema-agent/evals/care/report.md`: generated.

## Steps
1. Depth classification: accuracy per class; **D5 recall must be 100%** on red-flag cases, with zero LLM calls on them.
2. Handoff decision: precision/recall vs labels; list false negatives (should have handed off but answered).
3. Autonomy: simulate review streams → check promotion after N and demotion on serious edit.
4. Routing: simulate shifts/declines → chain always ends at on-call; SLA timing with fake clock.
5. Latency: p50/p95 for patient message → reply draft, with and without a specialist delegation; tick over 500 fake patients: wall time and LLM calls.
6. Cost: tokens per patient per month estimate from the above.
7. Reminder pause/reconcile: scenarios from M2c acceptance, counted.

## Acceptance
- `report.md` with all numbers above and the command lines used; failures listed plainly.
- D5 recall 100% and zero LLM calls on D5 cases, or the report explains why not and opens an item.

## Out of scope
- No tuning of model weights; prompt/config changes only, each recorded in the report.

## Report
Use `_REPORT-TEMPLATE.md` plus a link to `evals/care/report.md`.
