# Package O recipes — one identity, many operators (shared inbox)

One file = one step. Template: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report.
Source of truth: `pema-agent/docs/PLAN-AI01-O.md`; the plan wins over a recipe.

## Order

```
01-O1-channel-accounts-shifts ─► 02-O2-assignment-lock-takeover ─┬─► 03-O3-notifications ──┐
                                                                 └─► 04-O4-outbound-identity ┴─► 05-O5-fe-shared-inbox ─► 06-O6-eval-docs
```

## Locations

```
pema-agent/backend/apps/api/pema/ops/            package-O code: accounts.py shifts.py assignment.py lock.py takeover.py
                                                 notify/{service.py,kmp_push.py,zalo_fallback.py,team_group.py} outbound.py
pema-agent/backend/apps/api/alembic/versions/o_* migrations
pema-agent/backend/apps/api/tests/ops/           pytest
pema-agent/frontend/src/app/(admin)/inbox/**     shared inbox changes (O5)
pema-agent/frontend/src/app/(admin)/admin/ops/** channel accounts, shifts, notification settings (O5)
pema-kmp/                                        ONLY the push-token registration touchpoint (O3), documented, minimal
```

Reference (read-only): `pema/care/*` (routing, oncall, control), `pema/live/*` (presence, SSE), `pema/channels/*`
(zalo bot/personal adapters, send queue), `agent.accounts`/`agent.threads` models, `PLAN-AI01-M.md` §5–§7.

## Common rules

- Single-tenant: no RLS; `clinic_id` = installation id. Migrations prefix `o<step>_`.
- Operators never see credentials: no endpoint returns tokens/cookies; admin screens show status only.
- Notifications carry **no PII**: customer code, channel, urgency, masked one-line summary, deep link.
- No signature in outgoing text; sender shown to the customer is the channel account only.
- Synthetic data; no attribution in commits; report ≤ 30 lines with real test results (`_REPORT-TEMPLATE.md`).
