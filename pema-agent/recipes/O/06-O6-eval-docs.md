# O6 — Evaluation, load/race tests, docs and rules

## Goal
Prove the shared-inbox model under load and races, and write the rules that keep staff off personal Zalo.

## Read first
1. `PLAN-AI01-O.md` §8–§9; all O reports; `AGENT.md`, `pema-agent/docs/ARCH-AI01.md`, `SECURITY-REVIEW-AI01.md`.

## Steps
1. Load: 200 synthetic threads on one channel account, 5 operators, agent active → measure queue wait, send gap
   compliance, notification latency (push fake with timing), SLA escalations.
2. Races: simultaneous claims, takeover during send, shift end while typing, duplicate webhooks — assert invariants
   from O2/O4.
3. Security: credential boundary scan over OpenAPI responses and logs; PII guard on notifications; confirm
   `zalo_internal` cannot send to customers.
4. Docs: ARCH-AI01 (operators, channel accounts, notification chain), SECURITY-REVIEW (new findings as SEC-xx),
   `pema-agent/README.md` (operator onboarding: install app, register push, link Zalo fallback once),
   `AGENT.md` rule: "Staff never contact patients from personal accounts; all customer messaging goes through Pema
   channel accounts; personal Zalo receives notifications only (no PII)."
5. Report numbers.

## Acceptance
- All invariants hold under the race suite; numbers recorded; docs updated; rule added.

## Out of scope
- Facebook (package F).

## Report
Use `_REPORT-TEMPLATE.md` plus a link to the eval report.
