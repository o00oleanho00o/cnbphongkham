# U11 — Accountant role, finance period-close owner (owner-approved 2026-10-05)

## Goal
Add a seventh role, `accountant`, restoring a role the **old web already had** (`prototype/shared/staff-context.js`
account `{id:'accountant', role:'accountant', label:'Đối soát & thu ngân'}`), and make the accountant the one who
closes a finance period (with owner/manager able to override).

## Owner decision and one flagged deviation — read before coding
Owner decision 2026-10-05: "vai kế toán riêng" (yes), "thu ngân có được duyệt đơn không" (yes), "ai chốt kỳ" (bundled
into the same "yes"). Checked against the old web and the current code:
- **Dedicated accountant role: build it.** The old web's own role model already separates `accountant` from
  `reception`/`cs_staff` (it has no `reception`/`cashier` role at all — the cashier screens are reached by `owner`,
  `doctor` and `accountant`; `/cashier` pages in the new FE have so far used `reception` as the stand-in). This
  recipe adds `Role.ACCOUNTANT`, not a `cashier` role — "thu ngân" in this codebase has always meant the cashier
  *function*, done today by reception/manager/doctor/owner and from now on also by accountant.
- **Order approval stays doctor + owner only — this is a deviation from the literal "có" answer, flag it to the
  owner in the report.** Both the old web (`order-data.js#approveOrder`: `if (!actor || actor.role !== 'doctor' …)
  throw Error('Cần bác sĩ duyệt đơn.')`, and further narrowed to the assigned doctor) and the current backend
  (`pema/clinic/actions/orders.py`: "order.approve is held by the doctor and the owner") enforce this as a clinical
  safety rule (`AGENT.md`: doctor approves orders; never infer a prescription was dispensed because it was
  approved). Letting accountant/reception approve a prescription order would remove that control. Do **not** grant
  `order.approve` to `accountant` or `reception`. Accountant gets the billing side instead: raise/edit draft orders
  (`order.write`, already open to reception et al.), collect payment, raise invoices, see the catalog. If the owner
  confirms after reading this that non-doctors really should approve orders, that is a separate, explicit recipe —
  do not build it here.
- **Period close: accountant closes it** (`finance_period.close`); owner and manager can also close or re-open one
  (override, audited). This is the default in the absence of a more specific answer; note it as confirmed-by-default
  in the report, not as still-open.

## Read first
1. `prototype/shared/staff-context.js` (accounts, `pages`, `capabilities` — `billing: ['owner','accountant']`,
   `readFinance: ['owner','accountant','doctor']`; `home()` sends accountant to `cashier`).
2. `pema-agent/backend/packages/contracts/src/pema_contracts/roles.py` (`Role`, `STAFF_ROLES`, `Permission`),
   `pema-agent/backend/apps/api/pema/clinic/rbac/matrix.py`, `docs/ARCH-PB01.md` (role → permission table — this is
   a living contract doc, not the read-only PB01/PB02 spec prose; update its table, do not touch its narrative
   sections), `pema-agent/docs/CONTRACTS-AI01.md` §"Assignable roles"/`ASSIGNABLE_ROLES` (accountant must **not** be
   added there — no Inbox, no CRM queue, matching old-web `pages.accountant` having neither `crm` nor `followups`).
3. `pema-agent/backend/apps/api/pema/clinic/actions/finance.py` (docstring: "the accountant has no role of its own
   in this system: the manager holds finance.read/finance.collect" — this comment is the decision being reversed;
   update it), `finance_cash.py`, `pema-agent/backend/apps/api/pema/clinic/finance/domain.py`
   (`PERIOD_CLOSED_MESSAGE`, period lifecycle open/approved/closed).
4. FE: `pema-agent/frontend/src/components/admin/accounts/account-edit-drawer.tsx` (role picker),
   `pema-agent/frontend/src/lib/ops/staff-view.ts` (role labels/badges), `pema-agent/frontend/src/lib/session/session-context.tsx`.

## Ingredients
- `Role.ACCOUNTANT = "accountant"` added to the enum; `STAFF_ROLES` includes it. A small data migration is enough
  (role is stored as text, not a native Postgres enum type — confirm this before writing a migration and say so in
  the report).
- RBAC matrix: accountant gets `finance.read`, `finance.collect`, `finance_period.close`, `order.read`, `order.write`,
  `patient.read` (narrowed like reception, no clinical fields), `consent.read`; explicitly NOT `order.approve`,
  `session.write`, `media.write`, `admin.users`.
- `finance_period.close`: owner, manager, accountant (manager keeps the override it has today); audit records who
  closed/reopened.
- FE: role picker gains "Kế toán"; `/admin/users` and `/admin/accounts` list it; a new account with this role lands
  on `/cashier` first (matching the old web's `home()`), sees `/finance`, `/cashier`, `/patients`, `/patients/[id]`
  (billing tab from U9), `/guide` — not `/today`'s CRM queue, not `/inbox`, not `/crm` (matching old-web `pages`).
- Update the reversed decision's trail: `finance.py` docstring, `PLAN-AI01-U.md` (this file's own round-2 section
  already documents it — do not duplicate, just cross-reference).

## Steps
1. Add the role (contracts package, migration if one is actually needed, RBAC matrix, `ASSIGNABLE_ROLES` explicitly
   excludes it with a one-line reason).
2. Wire `finance_period.close`/`reopen` actions to the new permission; keep existing owner/manager behaviour.
3. FE role picker, labels, route guard (`guarded-link.tsx` / nav) for the new role's page set; empty states for
   pages it cannot see (403, not a broken page).
4. Tests: RBAC denial for `order.approve` by accountant (explicit, this is the safety-critical one), allow for
   `finance_period.close`/`finance.collect`, deny for `session.write`/`media.write`/`admin.users`; a synthetic
   accountant seed user.
5. `FEATURE-INVENTORY.md` rows; inventory + smoke + visual.

## Acceptance
- An accountant account can close a period, collect payment, raise an invoice and a draft order; cannot approve an
  order, write a session, upload media, or see Inbox/CRM/Today's CSKH queue.
- RBAC tests for every permission listed above, both directions (allow and deny); audit rows present.
- `ASSIGNABLE_ROLES` unchanged in membership (still owner, manager, doctor, cs_staff) with a test asserting
  accountant is excluded.

## Out of scope
- Letting accountant or reception approve orders (flagged above, needs an explicit owner recipe if wanted).
  MISA/accounting-software export. A `cashier` role distinct from accountant.

## Report
Use `_REPORT-TEMPLATE.md`; restate the order-approval deviation in your own words so the owner sees it without
reading this file, and confirm whether role is a text or native-enum column (and what you did either way).
