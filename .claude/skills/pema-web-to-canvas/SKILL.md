---
name: pema-web-to-canvas
description: Compare the Pema web (Clinic Web, Patient Mobile web, Finance) with the claude.ai/design canvas "Pema App.dc.html" — starting from the web-changes.md log and the git diff since the sync baseline instead of re-scanning everything — find web screens/tabs/dialogs that are missing or changed, build them into the canvas using the mobile app patterns (blocks implemented in KMP `core:ui`), check the render, then push to claude.ai/design. Use when asked "check which web screens are missing from the design", "convert web templates to the mobile design", "update the canvas from the web". Does not write app code.
---

> **Canonical skill (decision, package W2 step W12, 2026-10-05): not this one for the front end.** The canonical skill for "keep
> the canvases in step with the front end" is `pema-web-design` (`.claude/skills/pema-web-design/SKILL.md`), because the Next.js
> front end in `pema-agent/frontend` is now the product. This skill stays valid for its own job only: the **app** canvas
> `Pema App.dc.html` (82 screens) and the log `web-changes.md` for changes of `prototype/` (legacy web); treat it as app-only /
> legacy for anything about web canvases or the Next.js front end. The cross-index of app and web ids is
> `design-specs/INDEX.md`. No script was deleted.

# Pema web → mobile design canvas

The canvas `Pema App redesign canvas/Pema App.dc.html` is the design of the mobile app (`pema-kmp/`) and the place where new screens are designed first. This skill adds web screens the canvas lacks, **at the design level only**. App code is not touched; if needed, build the screen separately with the `pema-canvas-to-kmp-compose` skill.

Read first: `AGENT.md` (synthetic data, Patient 360, AI drafts need doctor review) and `.agents/skills/pema-design/references/visual-system.md` (Pema colors, type, radius).

Script paths are relative to the repo root: `S=.claude/skills/pema-web-to-canvas/scripts`. Keep temp files (dumps, screenshots) outside the repo (scratchpad or `%TEMP%`); never commit them.

## 1. Setup

| Need | Command | Check |
|---|---|---|
| Web prototype | `docker compose up -d pema-prototype` | http://127.0.0.1:4173/clinic-web/ |
| Design viewer (dev, hot-swap) | `cd design-viewer && npm run dev` | http://localhost:4180 |
| Playwright + Chromium | `npx -y playwright@latest install chromium` (once) | scripts find it in the npx cache; or set `PLAYWRIGHT_MODULE` |

Finance web needs `python prototype/finance_server.py` to show numbers. Without it the dump still lists the 4 tabs, and canvas group H already covers this area.

## 2. See what changed on the web since the last sync

**Start here; don't scan the whole web.** [web-changes.md](web-changes.md) is the log written by whoever changes the web (rule in `AGENT.md` › "Logging web changes for the design canvas"). Its **Sync baseline** line is the commit the canvas last matched.

```sh
node $S/pending.cjs      # "Pending" entries + web files changed since the baseline, ✗ = changed but not logged, suggested --only
```

- **No pending entries and no changed files** → report "canvas matches the web" and stop.
- **Pending entries**: read each one (where, change, canvas target) and open exactly those canvas screens.
- **`✗ NOT LOGGED` files**: read `git diff <baseline> -- <file>` (that file only), write the missing entry under "Pending" yourself, then handle it like any other entry.
- Only dump the related screens, using the `--only` command that `pending.cjs` prints:

```sh
node $S/dump-web.cjs "$TMP/web-dump.txt" --only=clinic:today,dialog:today
node $S/canvas.cjs list | grep -E '^(I2|I4) '           # see the matching canvas screens
```

**Full dump** (`dump-web.cjs` without `--only`, plus `canvas.cjs list`) only when: the log has no baseline; the baseline is no longer in git history; a shared token/shell changed (`design.css`, `ui.js`); or the user asks for a full review.

`dump-web.cjs` walks every `data-nav`, `data-tab`, `data-modal`, `data-screen`, `data-finance-tab` automatically. Dialogs opened by buttons ("Đặt lịch", "Thu tiền", "Xử lý"…) and mobile screens reachable only through a row inside another screen are declared at the top of the script (`CLINIC_DIALOGS`, `MOBILE_LINKS`). When the web adds a new button/screen, add it to those two lists. A `FAILED` line in the dump means a selector/button label changed: fix the script, don't skip it. When the web adds a new JS file, add a row to the `MAP` table in `pending.cjs`.

## 3. Find what is missing

Compare the dump (per log entry, or full) with [references/coverage.md](references/coverage.md) (web → canvas screen code table) and the matching canvas screens:

- **Covered**: the canvas has a screen with the same purpose **and** the same main fields/actions. A matching title is not enough; e.g. C6 is a reduced version, so the full CSKH form on the web still became I13.
- **Missing**: a web page, tab, modal or dialog with actions or data the canvas does not show.
- **Skip**: desktop-only parts (sidebar, demo account picker, calendar drag-and-drop) and app-only screens (end of coverage.md).

List for the user: web screen → why it is missing → planned canvas code, then continue. No need to stop for approval unless the scope is unusually large.

## 4. Build the screens into the canvas

Add data in the canvas `build()`, right before `const groups = [`. Block usage is in [references/blocks.md](references/blocks.md).

- **Groups**: keep A–H intact (core app screens). Append to I (Clinic operations), J (Patient 360), K (Pema Care), continuing the numbering (I14, J12…). Only open a new group (L…) for a genuinely new area; add it to `groups` and to the options of the `group` prop.
- **Only use existing blocks**, so every screen can be built with existing KMP `core:ui` components. Don't edit the HTML template unless a block is truly missing (see blocks.md).
- **Desktop to mobile** (per `pema-design`: child screens, short sheets, no desktop tables):

  | Web | Canvas |
  |---|---|
  | Multi-column table (reception, invoices) | `fc(...)`, one card per row: `ftitle` + `fl` + button `ff`/`fb` |
  | Room × time grid, week calendar | `week()` + `dd` room picker + `s(room)` + `t(time, …)` |
  | Filters / status tabs | `chips([...])`, selected item is `'sel'` |
  | KPI cards | `m(...)` at most 3 tiles, the rest as `t(...)` |
  | Modal with many inputs | its own `det(...)` screen with `dd`/`input`/`check` + `p(...)` |
  | Short choice (method, group) | `hasSheet` with radio `rows` |
  | Timeline / history | a series of `t(date · event, recorded by, icon, false)` |

- **Data**: use the canvas `pt`, `people`, `GROUPS`, `money()`; don't copy names or numbers from the web. Keep the web's business-rule sentences (in Vietnamese, verbatim): AI is only a draft, completed treatment is never inferred from payment, messages are not an emergency channel, illustrative photos don't score efficacy, CSKH doesn't send real Zalo/SMS.
- **Screen notes** start with `WEB + '<route/tab/modal> · <what differs when moved to mobile>'` so reviewers know the source.
- Update the intro sentence in `<header>` if a group's scope changes.

## 5. Check

```sh
node $S/canvas.cjs check "Pema App.dc.html" I,J,K "$TMP"   # exit 1 on errors
```

Passes when: `errors` is empty, `unresolved` is empty (no `{{ }}` left), `overflow` is empty, `total` = old count + added screens. Then **open every `canvas-<group>.png` and look**: text overflow, wrapped metrics, icons rendered as text (wrong name), FAB/sheet covering important content. Exit code 0 alone is not enough.

## 6. Push to claude.ai/design

Project: "Pema App redesign canvas", id `7822035f-ae10-4b1f-a802-ce789b25a393` (a regular project, not a design system). The `DesignSync` tool is only used inside the `/design-sync` flow started by the user; if they haven't started it, remind them. In that flow, **only update the file you edited**:

1. `DesignSync get_file` that file. Large results are saved to a JSON file.
2. `node $S/remote-diff.cjs <JSON file> "Pema App redesign canvas/Pema App.dc.html"`. `-` lines are edits that exist only on claude.ai/design: merge them into local (or ask the user) before overwriting. No `-` lines means it is safe.
3. `finalize_plan` with `localDir` = the canvas folder, `writes: ["Pema App.dc.html"]`, `deletes: []`, then `write_files` with `localPath`.
4. `get_file` again and compare with the local file (ignoring CRLF differences) to confirm they match.

Never delete remote files, never create `.design-sync/config.json`, never run the design-system build flow.

## 7. Finish

- The Docker viewer (localhost:4190) bundles the canvas at build time: `docker compose up -d --build pema-design-viewer`.
- Update [references/coverage.md](references/coverage.md) (date, total screen count, new rows).
- Update [web-changes.md](web-changes.md): move each finished entry from "Pending" to the top of "Done", adding `- Result: <canvas codes added/changed>, pushed/not pushed to claude.ai/design`. Change **Sync baseline** to the web commit you compared against (`git rev-parse --short HEAD`, or the commit created below if the web change is not committed yet). Leave unfinished entries under "Pending" with the reason. Rerun `pending.cjs`: it must report 0 pending entries and 0 `✗` files.
- Per `AGENT.md` for UI-only changes: append a checkpoint to `SECTION_PROGRESS.md` (screens added, viewport 390×844, how it was checked). Don't record app features as existing just because the canvas has the screen.
- `git diff --check`, then commit the canvas + coverage + web-changes files, e.g. `design: add web-only screens to Pema App canvas`. Never commit dumps or screenshots.
- Report: screens added per group, the `check` result, pushed/not pushed to claude.ai/design, and what remains (e.g. the clickable `Pema Prototype.dc.html` doesn't have the new screens yet).
