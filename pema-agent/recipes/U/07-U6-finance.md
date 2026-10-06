# U6 — Finance (PB02) ported into the BE and the Next.js FE

## Goal
Replace `prototype/finance_server.py` + `prototype/finance/` with `pema/clinic/finance` and `/finance/*` screens,
keeping every PB02 rule and proving equivalence with `prototype/finance_test.py`.

## Read first
1. `PLAN-AI01-U.md` §3 row finance.
2. `AGENT.md` "PB02 finance rules" (read SCOPE/SPEC/MODULEMAP/ARCH-PB02 in order), `docs/24_FINANCE_AND_PROCEDURE_FEES.md`,
   `prototype/finance_server.py` (Finance.view/command/mutate, role projections, periods, notifications),
   `prototype/finance_test.py`, `prototype/shared/care-finance.js`, `finance-bridge.js` (what the web mirrors).
3. U4 services (rate, basis, version) and U5 orders (invoice link).

## Ingredients
- Migration `u6_0010_finance.py`: `clinic.invoice`, `clinic.payment`, `clinic.procedure_entry` (performed revenue with
  rate snapshot per person), `clinic.finance_period` (open/approved/closed), `clinic.finance_notification`.
- `pema/clinic/finance/`: pure domain (money rounding `(base*rate+5000)//10000`, no mixing performed revenue with
  collected cash, duplicate-collection and overpayment guards, closed period immutable, performing doctor never
  auto-assigned), actions per role projection (owner, accountant, doctor), export CSV with formula-injection guard.
- Routers `finance.py`; pages `/finance` (overview per role), `/finance/entries`, `/finance/payments` (inbox),
  `/finance/periods` (approve/close month), `/finance/export`.

## Steps
1. Port `finance_test.py` cases to pytest **first**; they must fail, then pass against the new module.
2. Domain + actions + migration; RBAC per role; audit every mutation.
3. Pages with the kit; role switch comes from the real session, not a header.
4. Link invoices to U5 orders and U4 services; keep rate snapshots on entries.
5. Inventory rows + smoke tests. Note in the report that `finance_server.py` remains in the repo, unused by the new FE.

## Acceptance
- Ported equivalence tests green; additional tests for closed-period immutability and overpayment.
- FE: finance pages at 5 viewports; inventory green; vitest ≥ baseline.

## Out of scope
- MISA / e-invoice export (open item for the owner). Deleting the old finance server.

## Report
Use `_REPORT-TEMPLATE.md`; list any PB02 behaviour that could not be reproduced exactly.
