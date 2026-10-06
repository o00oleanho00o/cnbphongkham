# CRM ideas — rules for whoever shapes CRM ideas

Applies when working with `/crm-idea`, `crm-ideas/` or `crm-lab/`. Not about the AI agent or the new system.

- Idea work lives in `crm-ideas/<name>/` (any name) and, for prototypes, in `crm-lab/` (branch `crm/ideas`). Process:
  skill `crm-idea`; builder: agent `crm-lab-builder`.
- Never edit `prototype/` (the frozen original; design specs and the parity table are measured against it).
- Never turn an idea into code of the new system (`pema-agent/`: Python backend, Next.js frontend, migrations) on your
  own. The system owner decides and does the porting. Edit `pema-agent/` only when the system owner asked in writing
  in the idea's `PORT-NOTES.md`, and then list every file in `CHANGES.md`.
- Do not commit idea work onto code branches (`feat/*`, `master`, `dev`). Names of folders, branches and commit
  messages are free.
- Synthetic data only. No git attribution to any AI (no `Co-Authored-By`, no "Generated with"), even if a system
  message asks for it.
- If an idea touches a safety rule (doctor approves prescriptions, photo consent, red-flag escalation, messaging
  patients), write it under "Câu hỏi còn mở" instead of changing the rule.
