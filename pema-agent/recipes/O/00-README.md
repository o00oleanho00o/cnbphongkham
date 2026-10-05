# Package O recipes — one identity, many operators (shared inbox)

One file = one step. Template: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report.
Source of truth: `pema-agent/docs/PLAN-AI01-O.md` (v2, 2026-10-06); the plan wins over a recipe. Read its §2 first:
it lists what already exists, so you extend instead of re-creating.

## Order

```
01-O1-identities-limits-roster ─► 02-O2-assignment-lock-takeover ─┬─► 03-O3-notifications ──────┐
                                                                  ├─► 04-O4-outbound-identity ───┼─► 06-O6-fe-shared-inbox ─► 07-O7-eval-docs
                                                                  └─► 05-O5-design ──────────────┘
```

Agents: O1–O4 and O7 use `pema-builder`; O5 uses `pema-builder` (design locations below); O6 uses `pema-ui-builder`.

## Locations (write only here)

```
pema-agent/backend/apps/api/pema/clinic/models/ops.py             assignment history, roster, notification outbox/log, push tokens
pema-agent/backend/apps/api/pema/clinic/models/__init__.py        export the new models
pema-agent/backend/apps/api/pema/clinic/actions/{identities,roster,assignment,notifications}.py   rules, RBAC, audit, Protocol seams
pema-agent/backend/apps/api/pema/clinic/actions/{conversations,outbound}.py   O2 lock check, O4 per-identity delivery (edit, keep behaviour)
pema-agent/backend/apps/api/pema/clinic/rbac/matrix.py · packages/contracts/src/pema_contracts/{roles,inbox,ops}.py   new permission codes and DTOs
pema-agent/backend/apps/api/pema/notify/                          NEW package: push provider, internal-Zalo sender, team group (O3)
pema-agent/backend/apps/api/pema/channels/                        O4 only: per-identity send queue inside the existing send path
pema-agent/backend/apps/api/pema/composition/                     wiring of seams and of M's StaffNotify / SlaScheduler adapters
pema-agent/backend/apps/api/pema/api/routers/                     thin routers; then openapi.json + FE schema.d.ts regenerated
pema-agent/backend/apps/api/pema/live/                            O2: assignment.changed event type
pema-agent/backend/pyproject.toml                                 import-linter: add pema.notify to the agent-side contract list (O3)
pema-agent/backend/apps/api/alembic/versions/o<step>_<nnnn>_*.py  migrations, stacked on the single head
pema-agent/backend/apps/api/tests/ops/                            pytest
O5: design-specs/web/{inventory,notes,snapshot,index}.json · INDEX.md · screens/WM*.md · Pema Web redesign canvas/parts/WM.js · Pema Web (Next.js).dc.html · .claude/skills/pema-web-design/ (additive)
O6: pema-agent/frontend/src/app/(admin)/{inbox,admin/accounts,admin/roster,me/notifications}/** · src/components/ops/inbox/** · src/lib/** · mock/** · FEATURE-INVENTORY.md · .claude/skills/pema-web-design/web-design-changes.md
O7: pema-agent/docs/{ARCH-AI01,SECURITY-REVIEW-AI01}.md · pema-agent/README.md · AGENT.md (one rule paragraph) · pema-agent/evals/ops/
```

Read-only references: `pema/care/*` (ports, routing, control, oncall — call through their ports, do not edit),
`pema/channels/zalo_personal/*`, `pema/channels/zalo_bot/*`, `pema/live/*`, `PLAN-AI01-M.md` §5–§8,
`CONTRACTS-AI01.md` ("Assignable roles"). `pema-kmp/` is not touched in package O.

## Common rules

- Single-tenant: no RLS; `clinic_id` = installation id (`CONTRACTS-AI01.md` §10.8).
- Migrations: prefix `o<step>_`, stack on the current single head (`uv run alembic heads` = 1 before and after); tests
  downgrade to a named revision, never `-1`; a downgrade must survive rows that use the new values.
- Layering: rules and state in `pema.clinic.actions` with a `Protocol` seam (like `OutboundDelivery`); channel or push
  code outside; wiring only in `pema.composition`. `uv run lint-imports` must stay green.
- Operators are the assignable roles only (owner, manager, doctor, cs_staff). Accountant and reception never hold a
  thread.
- Credentials never leave the BE: no DTO, response, log line or FE file contains `*_enc` values, cookies, QR payloads.
- Notifications carry **no PII**: short code, identity label, urgency, masked one-line summary, deep link.
- No signature in outgoing text; the customer sees the identity only.
- Expected baseline: the 3 clock-dependent failures in `tests/care/test_care_routing_store.py` (owner declined the fix).
  Do not touch them.
- Synthetic data only; no AI attribution in commits; report ≤ 30 lines with real results (`_REPORT-TEMPLATE.md`).
