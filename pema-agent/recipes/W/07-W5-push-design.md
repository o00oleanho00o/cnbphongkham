# W5 — Push the web canvas to claude.ai/design (director with the user, not a subagent) — OPTIONAL

The canvas already runs locally: `docker compose up -d --build pema-web-design-viewer` (repo root) serves it at http://127.0.0.1:4191/
(the app canvas stays at 4190). Do W5 only if the owner wants the canvas on claude.ai/design too.

## Goal
Put `Pema Web redesign canvas/Pema Web.dc.html` and its `support.js` on claude.ai/design as their own project, and
prove that the remote copy equals the local copy.

## Why not a subagent
The `DesignSync` tool works only inside the `/design-sync` flow that the **user** starts. Creating the project is a
user action on claude.ai, and the push publishes content. Each of these needs the user present.

## Steps
1. The user creates the project "Pema Web redesign canvas" on claude.ai/design (decision D7), or names an existing one.
   Record its id in `.claude/skills/pema-web-design/SKILL.md` §6.
2. The user starts `/design-sync`. Then, in the flow:
   1. `DesignSync get_file` for `Pema Web.dc.html`. On a new, empty project there is nothing to merge. If the file
      exists, run `node .claude/skills/pema-web-to-canvas/scripts/remote-diff.cjs <json> "Pema Web redesign canvas/Pema Web.dc.html"`
      and merge every `-` line into the local file before overwriting.
   2. `finalize_plan` with `localDir` = `Pema Web redesign canvas`, `writes: ["Pema Web.dc.html", "support.js"]` and
      `deletes: []`, then `write_files`.
   3. `get_file` again and compare with the local file, ignoring CRLF. They must be equal.
3. Open the project on claude.ai/design with the user. Check one frame per group at 1440, and one page at 390.
4. Never delete remote files. Never create `.design-sync/config.json`. Never run the design-system build flow. Never
   touch the app project `7822035f-ae10-4b1f-a802-ce789b25a393`.

## Acceptance
- Remote = local, with the comparison output saved in the report.
- The project id is written in SKILL.md.
- The HANDOFF "Package W" result line is written: pushed, with the date.

## After W5
- Merge `feat/web-design` into `feat/ui-parity` when the user accepts the package. Push only when the user says so.
- Tell U4–U8 builders to read `get_web_screen(<ID>)` before porting. Add one line in `recipes/U/00-README.md` after the
  user agrees.
