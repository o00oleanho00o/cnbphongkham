# W6b — Shots and specs for the new ids (two agents in parallel: SHOTS and SPECS)

Input: the inventory after W6a. `new ids` = the ids that were not in the W0 inventory (group WI and the appended ids).
Run both agents at once. Each uses at most ONE browser on the old web. The director starts a second old-web server on port 4175
for the SPECS agent (`python -m http.server 4175 --bind 127.0.0.1 --directory prototype`). SHOTS uses 4173. The inventory
`base_url` stays 4173: the SPECS agent passes `--base-url http://127.0.0.1:4175` (add the flag to the scripts if missing).

## Agent SHOTS (`recipes/W/02-W1-old-web-shots.md`, restricted to the new ids)
- `web-shots.cjs --only=<new ids>` for all five viewports. For native-dialog ids, follow W6a (page plus captured message).
- Update `manifest.json` for the new ids only (existing entries untouched), the gallery, and the legacy names if a new id has
  `legacy_shot`.
- Write PNGs to the main checkout folder
  `C:/Users/phanx/Documents/Codex/2026-09-11/create-an-image-of/cnbphongkham/pema-agent/frontend/visual-ref/old/` with `--out`,
  not to the worktree.
- Open and look at one image per new group at 1440, and every WI image at 390.
- Acceptance: 5 shots per new id, 0 page errors, manifest SHAs equal to the files, and
  `web-coverage.cjs --check --images=<that folder>` passes.

## Agent SPECS (`recipes/W/03-W2-web-specs.md`, restricted to the new ids)
- `web-snapshot.cjs --only=<new ids>`, merged into `snapshot.json` (existing ids byte-identical).
- Seed `notes.json` for the new ids: source function, rule sentences, differences from the app design, `native` texts.
- Then `web-specs.cjs` for the new specs, and `web-specs.cjs --check`. Mask volatile data (random ids, dates, finance debt) as W2 did.
- The MCP tools must list and return the new ids.
- Acceptance: spec count = inventory count; `--check` exits 0 with 0 missing items; `get_web_screen("WI1")` works.

## Both
Own files only.
- SHOTS: `visual-ref/old/manifest.json`, `web-shots.cjs`, README.
- SPECS: `design-specs/web/{snapshot,notes}.json`, `INDEX.md`, `index.json`, `screens/`, and the snapshot and specs scripts.

Worktrees `C:/wt/pema-w6b-shots` and `C:/wt/pema-w6b-specs` (branches `design/w6b-shots`, `design/w6b-specs`). Same rules and report
format as W1 and W2.
