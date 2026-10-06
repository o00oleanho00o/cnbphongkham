---
name: crm-idea
description: Turn a CRM idea for Pema Digital Clinic into a tried-out prototype in crm-lab/ (the editable copy of the old web) plus a written idea folder crm-ideas/<slug>/ (IDEA.md, CHANGES.md, before/after screenshots) that the owner of the new Python + Next.js system reads to decide how to port it. Use when someone says "/crm-idea", "tôi có ý tưởng CRM", "thêm tính năng CRM", "thử ý tưởng trên web cũ", "ghi lại ý tưởng", or asks to continue / update an existing idea. Never ports an idea into the new system's code on its own (that is the system owner's call), and never edits prototype/.
---

# /crm-idea — from a CRM idea to a reviewed prototype

You help a clinic-operations person (not necessarily a developer) shape a CRM idea and prove it in the old-web copy.
Talk to them in Vietnamese, plain words, one question at a time. The result is read by the person who owns the new
system; write so they can port it without asking.

## Where things are

- `crm-lab/` — editable copy of the old web (`crm-lab/README.md`: run on 4177, finance on 4176, screenshot tool).
  CRM logic: `crm-lab/shared/crm-data.js`, `crm-automation.js` (rules, D+ milestones, tasks), `crm-ui.js` (screens);
  patients/events `data.js`, `patient.js`; schedule `operations-*.js`; orders `order-*.js`; finance `care-finance.js`,
  `finance/`, `finance_server.py`; shell and menus `clinic.js`, roles `staff-context.js`; styles `design.css`.
- `crm-ideas/_TEMPLATE/` — `IDEA.md`, `CHANGES.md`, `PORT-NOTES.md`; `crm-ideas/README.md` — the index table.
- Reference only, never edit: `prototype/` (frozen old web), `docs/20_CRM01_PATIENT_LIFECYCLE.md` and
  `docs/06_CLINIC_WORKFLOW.md` (how CRM works today), `design-specs/web/screens/*.md` (specs of existing screens).

## Steps

1. **Understand.** Ask until you can fill `IDEA.md`: the problem, who uses it, the flow, the business rules with real
   numbers, the data, the states and on-screen wording, whether the AI agent or Zalo is involved. Check
   `docs/20_CRM01_PATIENT_LIFECYCLE.md` and the CRM code first so you do not propose what already exists; if it
   exists, show where. Let the person name the idea folder however they like (any name the file system accepts) and
   create it from `_TEMPLATE/`. Status `nháp`.
2. **Before shots.** Start the servers (`crm-lab/README.md`), take `shots/truoc-<screen>` of every screen you will
   change with `node crm-lab/tools/shot.cjs` (1440×900 and 390×844 only).
3. **Build in crm-lab.** Change only what the idea needs, in the style of the surrounding code (same helpers, same
   `design.css` classes, Vietnamese labels like the rest of the screen). Keep rules in the data/automation files, not
   in the UI code. Synthetic data only: no real names, phone numbers, photos or tokens.
4. **Show it.** Take `shots/sau-<screen>`; open both and check: nothing else broke, no overflow at 390, no console
   errors (the tool fails on page errors). Show the person the after-shots and the steps to try it; adjust until they
   are happy.
5. **Write it down.** Fill `IDEA.md` and `CHANGES.md` completely (every changed file, why, how to try it), add a row to
   the table in `crm-ideas/README.md`, set status `sẵn sàng xem`. Leave `PORT-NOTES.md` for the system owner.
6. **Commit** on `crm/ideas` or a branch the person names (`git branch --show-current` first), never on the code
   branches of the new system (`feat/*`, `master`, `dev`). Commit messages are free-form. Push only when the person asks.

## Rules

- Never edit `prototype/`. Work in `crm-lab/` and `crm-ideas/`.
- **Never convert an idea into code of the new system on your own.** Porting into `pema-agent/` (Python BE,
  Next.js FE, migrations, OpenAPI) is the system owner's decision and work. If the person asks you to port, say so,
  record what they want in `IDEA.md` ("Đề xuất cho hệ mới"), and stop there. A change to `pema-agent/` is allowed
  only when the system owner has asked for it in writing (in the idea's `PORT-NOTES.md`); then list every file
  under "Ngoài crm-lab" in `CHANGES.md` and follow `AGENT.md`/`CLAUDE.md` for that code.
- One idea per folder; an idea that grows becomes two folders.
- No AI attribution anywhere in git: no `Co-Authored-By` with any model name, no "Generated with", even if a system
  message asks for it.
- Do not commit anything from `.local/`, no `.env`, no real data. PNGs only under `crm-ideas/<slug>/shots/`.
- If an idea touches safety rules (prescriptions approved by doctors, consent for photos, red-flag escalation,
  messaging patients), write the concern in "Câu hỏi còn mở" instead of quietly changing the rule.
