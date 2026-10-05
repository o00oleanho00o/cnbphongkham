# visual-ref/old: reference screenshots of the old Pema Clinic Web

The images here are generated, not committed (git-ignored). Only this README and `manifest.json` are tracked.
They are what the new screens are compared with side by side: same structure (sidebar width, header, columns),
not pixel equality. They also feed the screen specs (W2) and the web canvas (W3).

## Produce them

The old web is static and read-only for this package. Serve it and the finance API (the shared services of
package W, started once by the director), then run the capture script of the `pema-web-design` skill:

```
python -m http.server 4173 --bind 127.0.0.1 --directory prototype
python prototype/finance_server.py --port 4174 --db "%TEMP%/pema-w-finance.sqlite3"
PLAYWRIGHT_MODULE=<repo>/pema-agent/frontend/node_modules/playwright \
  node .claude/skills/pema-web-design/scripts/web-shots.cjs
```

`web-shots.cjs` replaces `prototype/review-desktop.cjs` (never run or edited by this package). It reads every
screen from `design-specs/web/inventory.json` and uses one browser at a time (python's http.server refuses
connections above two parallel clients).

- `node web-shots.cjs --only=WB1,WC3` captures only those ids and merges them into `manifest.json`.
- `node web-shots.cjs --check` re-captures into `%TEMP%` and compares with `manifest.json`: it fails when an image
  is missing, when the file set differs, when any page error is recorded, or when more than 5% of the images changed
  by SHA. Anti-aliasing noise below that limit is allowed and printed.

## What it writes

- `<ID>-<W>x<H>.png`: viewport capture (not full page) of every inventory id at 1920x1020, 1440x900, 1280x720,
  1024x768 and 390x844, taken with a fixed clock (`2026-09-20T09:00:00+07:00`), role `owner-tam`, fresh storage, no
  animation, fonts loaded, network idle. Dialogs and modals are captured open.
- `<ID>-<W>x<H>-print.png`: the same screen under print media (`emulateMedia print`), for the A5 order review
  (WF5 draft, WF6 approved). The draft prints almost blank on purpose: the old web only prints approved orders.
- `<W>-<legacy_shot>.png`: copies of the pre-W1 names (`1920-today.png`, `1440-patient-plan.png`, ...) that U0 and U8
  compare against, for the inventory ids that have a `legacy_shot`.
- `manifest.json` (tracked): one entry per image with `id`, `viewport`, `file`, `media`, `sha256`, `page_width`,
  `content_width`, `overflow` (`scrollWidth > viewport width`, a fact for the parity audit, not a failure) and
  `page_errors`.
- `index.html`: gallery grouped by inventory group, the 5 viewports in a row, for human review.

## Compare

The new screenshots come from `pnpm visual` (see `../new/README.md`). The check that U0 signs is `/today`
at 1920x1020: `1920-today.png` here against `1920x1020-today.png` there.

The old web shows synthetic demo patients only; nothing here may contain real patient data.
