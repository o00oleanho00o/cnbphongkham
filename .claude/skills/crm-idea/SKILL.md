---
name: crm-idea
description: Guide a person with a CRM idea for Pema Digital Clinic from a rough thought to a reviewed prototype and a written idea folder (crm-ideas/<name>/IDEA.md, CHANGES.md, before/after screenshots) that the owner of the new Python + Next.js system reads to decide how to port it. Use when someone says "/crm-idea", "tôi có ý tưởng CRM", "thêm tính năng CRM", "thử ý tưởng trên web cũ", "ghi lại ý tưởng", or wants to continue or update an existing idea. The prototype is built in crm-lab/ (editable copy of the old web, branch crm/ideas) by the agent crm-lab-builder. Never ports an idea into the new system's code on its own and never edits prototype/.
---

# /crm-idea — from a CRM idea to a reviewed prototype

You help a clinic-operations person (not necessarily a developer). Talk to them in Vietnamese, plain words, one
question at a time. The person who owns the new system (`pema-agent/`: Python backend, Next.js frontend) reads what
you write and decides how to port it, so write for that reader. The rules in `.claude/rules/crm-ideas.md` apply
throughout.

## Where things are

- `crm-ideas/_TEMPLATE/` — `IDEA.md`, `CHANGES.md`, `PORT-NOTES.md`; `crm-ideas/README.md` — the index table.
  Each idea gets its own folder `crm-ideas/<name>/`, named however the person likes.
- `crm-lab/` — editable copy of the old web, **only on branch `crm/ideas`** (and branches made from it). Its README
  says how to run it (web 4177, finance 4176) and how to take screenshots. CRM logic: `crm-lab/shared/crm-data.js`,
  `crm-automation.js`, `crm-ui.js`; patients `data.js`, `patient.js`; schedule `operations-*.js`; orders `order-*.js`;
  finance `care-finance.js`, `finance/`; menus `clinic.js`; roles `staff-context.js`; styles `design.css`.
- Reference only: `prototype/` (frozen old web), `docs/20_CRM01_PATIENT_LIFECYCLE.md`, `docs/06_CLINIC_WORKFLOW.md`
  (how CRM works today), `design-specs/web/screens/*.md` (specs of existing screens).

## Steps

0. **Preflight.** `git branch --show-current`. If `crm-lab/` is missing you are on a code branch (`feat/*`, `master`,
   `dev`): do not copy it in. Tell the person to run `git fetch` and `git switch crm/ideas` (or a branch made from it),
   then continue there. Never commit idea work onto a code branch.
1. **Understand.** Ask until you can fill `IDEA.md`: the problem, who uses it, the flow, the business rules with real
   numbers, the data, the states and on-screen wording, whether the AI agent or Zalo is involved. Read
   `docs/20_CRM01_PATIENT_LIFECYCLE.md` and the CRM code first so you do not propose what already exists; if it
   exists, show where. Create `crm-ideas/<name>/` from `_TEMPLATE/`, status `nháp`, and write what you learned.
2. **Build and show (delegate).** When `IDEA.md` is clear enough to build, hand the folder to the agent
   `crm-lab-builder` (Agent tool, `subagent_type: crm-lab-builder`) with the folder path. It takes the before
   screenshots, changes `crm-lab/`, takes the after screenshots and fills `CHANGES.md`. Then show the person the after
   screenshots and the steps to try it; ask what to change; repeat step 2 until they are happy.
3. **Hand over.** Check `IDEA.md` and `CHANGES.md` are complete (every changed file with a reason, how to try it, open
   questions), add a row to the table in `crm-ideas/README.md`, set the status line of `IDEA.md` to `sẵn sàng xem`.
   Leave `PORT-NOTES.md` for the system owner.
4. **Commit** on the current idea branch (`crm/ideas` or one the person names), free-form message. Push only when the
   person asks.

If the person asks you to build the idea into the new system, do not: write the wish under "Đề xuất cho hệ mới" in
`IDEA.md` and say that the system owner decides and does the porting.
