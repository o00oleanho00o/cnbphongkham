# O7 — Evaluation, load and race suites, security scan, docs and the AGENT.md rule

## Goal
Prove the shared-inbox model under load and races, and write down the rules that keep staff off personal Zalo.

## Read first
1. `PLAN-AI01-O.md` §6–§7; all O reports; `AGENT.md`; `pema-agent/docs/{ARCH-AI01,SECURITY-REVIEW-AI01,CONTRACTS-AI01}.md`;
   `pema-agent/README.md`; `pema-agent/evals/care/*` (structure to copy).

## Steps
1. `pema-agent/evals/ops/`: 200 synthetic threads on one identity, 5 operators, agent sending too → queue wait, gap
   compliance per identity, notification latency per provider (fakes, timed), escalations reached.
2. Race suite: simultaneous claims, takeover during send, end_shift while typing, duplicate inbound webhooks, two
   devices of one operator — assert the O2/O4 invariants.
3. Security: credential-boundary scan over every OpenAPI response schema and captured logs; PII guard over every
   notification kind; internal account never customer-facing; accountant/reception cannot claim or send.
4. Docs: ARCH-AI01 (identities, operators, assignment, notification chain, which M ports now have adapters);
   SECURITY-REVIEW-AI01 (new SEC-xx rows); CONTRACTS-AI01 (new endpoints and events); `pema-agent/README.md`
   (operator onboarding: sign in, link the Zalo bell once, push when the app supports it); `AGENT.md` rule:
   "Staff never contact patients from personal accounts; all customer messaging goes through Pema identities;
   personal Zalo only receives PII-free notifications."
5. HANDOFF-ready summary of what still needs M7 (care loop) and the KMP push client.

## Acceptance
- All invariants hold in the race suite; numbers recorded in `evals/ops/report.md`; docs and the rule updated.

## Out of scope
- Facebook (package F); KMP client; M7 wiring.

## Report
Use `_REPORT-TEMPLATE.md` plus a link to `evals/ops/report.md`.
