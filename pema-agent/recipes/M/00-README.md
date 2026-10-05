# Package M recipes — per-patient care agent

One file = one step. Same template everywhere: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report. A subagent takes **one file** and returns a report using `_REPORT-TEMPLATE.md`.

Source of truth: `pema-agent/docs/PLAN-AI01-M.md`. If a recipe and the plan disagree, **the plan wins**; note the conflict in the report.

## Order and dependencies

```
01-M1-schema ─┬─► 02-M2a-event-loop ─┬─► 03-M2b-control-handoff ─► 04-M2c-routing-oncall ─┐
              │                      │                                                     ├─► 07-M5-frontend ─► 08-M6-eval
              └─► 05-M3-autonomy ────┴─► 06-M4-specialists ────────────────────────────────┘
```

| File | Step | Needs first | Parallel with |
|---|---|---|---|
| `01-M1-schema.md` | Tables, migration, auto-pairing | A, B1 | — |
| `02-M2a-event-loop.md` | Event-driven turns, 06:00 tick, priority, send window, caps | M1, D1, S | M3 |
| `03-M2b-control-handoff.md` | State machine AUTO/HANDOFF_ROUTING/STAFF, `handoff` skill, depth classifier | M2a, P | M3 |
| `04-M2c-routing-oncall.md` | Staff routing, SLA, candidate chain, 24/7 on-call, reminder pause/reconcile | M2b | M4 |
| `05-M3-autonomy.md` | Levels L0–L2, trust scores, time-boxed override, kill switches | M1 | M2a, M2b |
| `06-M4-specialists.md` | Scheduler/Knowledge/Reviewer agents, `TaskResult`, budgets | M2a, M3, D1 | M2c |
| `07-M5-frontend.md` | Supervision and admin screens | M2c, M3, M4, E | — |
| `08-M6-eval.md` | Metrics and real-number report | all | — |

## Code locations (shared by all steps)

```
pema-agent/backend/apps/api/pema/care/        all package-M code
  models.py pairing.py ports.py loop.py tick.py priority.py
  control.py handoff_skill.py depth.py routing.py oncall.py reminders.py
  autonomy.py trust.py specialists/ budget.py task_result.py
pema-agent/backend/apps/api/alembic/versions/  agent.* migrations, prefix `m_`
pema-agent/backend/apps/api/tests/care/        pytest for package M
pema-agent/frontend/src/app/(ops)/care/        package-M screens
pema-agent/evals/care/                         labelled cases and measurement scripts
```

## Common rules (from PLAN-AI01 §7 and AGENT.md)

- Create/modify files only under `pema-agent/`. Everything else is read-only.
- Touch only your step's directories plus tests. Need a change elsewhere → list it under "Open items", do not make it.
- If an interface from another package (D1 `HarnessProcessor`, S scheduler, P profiles, B1 actions) is **not in HEAD yet**: define a thin `Protocol` in `pema/care/ports.py`, code against it, say so in the report. Do not wait, do not reimplement the other package.
- All test data is synthetic. No real phone numbers or names. The on-call number in tests is fake and flagged `is_fixture=True`.
- Python: uv, ruff, pyright strict, pytest, SQLAlchemy async. No `print`. Logger never logs PII.
- No scope creep: no images, no payments, no fine-tuning, no auto-send beyond the autonomy level.
- Report ≤ 30 lines using `_REPORT-TEMPLATE.md`, with **real** test results (failures included).
