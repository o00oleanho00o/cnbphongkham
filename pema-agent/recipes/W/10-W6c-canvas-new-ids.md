# W6c — Canvas frames for the new ids (parallel agents, one part file each)

Same mechanism as W3b (`recipes/W/05-W3b-canvas-screens.md`): each agent owns exactly one part file and its own ids' keys in
`design-specs/web/notes.json`.

| Agent | Owns | Ids |
|---|---|---|
| W6c-0 (runs first, alone) | `template.html`, `nodes.html`, `parts/base.js`, canvas scripts, `blocks-web.md` | adds group WI to the build, a phone-frame mode (390×844 and a centred phone column at 1440×900) and every block Patient Mobile needs (bottom nav, sheet, stepper, photo grid, toast…); creates stubs `parts/WI.js`, `parts/WI2.js` |
| W6c-WI-1 | `parts/WI.js` | WI ids for home, appointments, journey, progress, care |
| W6c-WI-2 | `parts/WI2.js` (merged into group WI by the build script) | WI ids for send, messages, docs, profile, privacy, and every WI modal and state |
| W6c-OPS | the new ids appended in `parts/WA.js`, `WB.js`, `WD.js` | new WA, WB, WD ids (empty states, errors, roles, native dialogs) |
| W6c-REST | the new ids appended in `parts/WC.js`, `WE.js`, `WF.js`, `WG.js`, `WH.js` | new WC, WE, WF, WG, WH ids |

After W6c-0 merges, the other four run in parallel, each with its own design-viewer port (4183–4186).

Rules, checks and report: as W3b.
- Every new id must pass `web-canvas.cjs check --complete` and `web-specs.cjs --check`.
- Native dialogs are drawn with the captured text.
- Error lines are drawn as the state frame the id describes.
- Look at every PNG.

Final director steps: merge, `web-canvas-build.cjs`, `web-specs.cjs`, `web-coverage.cjs`, rebuild the Docker viewer, update HANDOFF.
