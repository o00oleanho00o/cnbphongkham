# Web → design canvas change log

Sync baseline: `1564115`

Every time a screen, tab, modal, dialog, field, action or business-rule sentence **visible** on the Pema web (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`) is added, changed or removed, add an entry under **Pending** and commit it together with the web change. The `pema-web-to-canvas` skill reads these entries and only dumps/edits the affected screens instead of re-scanning the whole web.

**Log**: added or removed screen/tab/modal/dialog · added/removed/changed field, button, filter, status · changed flow (which screen a button opens, where saving goes) · changed warning/business-rule wording (AI draft, consent, not an emergency channel…) · changed color/type/radius token in `design.css`.
**Don't log**: refactors with no UI change · tests/evidence · seed/sample data (unless it adds a new column/status) · fixes with no visible change.

Template (newest entry on top):

```md
### YYYY-MM-DD · <add|change|remove> · <screen/tab/modal name>
- Where: `prototype/shared/<file>` · selector `data-nav="…"` / `data-tab="…"` / `data-modal="…"` / button "…"
- Change: <which field/button/status/sentence was added, removed, changed; new flow>
- Canvas target: <screen code from references/coverage.md, e.g. I2, J6 · or "new screen">
- Logged by: <name/agent> · commit/PR if any
```

If unsure of the canvas code, write "unknown"; the skill looks it up in `references/coverage.md`. Keep Vietnamese UI labels and wording exactly as they appear on the web.

## Pending

### 2026-10-01 · change · Hướng dẫn › Mobile, CSKH & tài chính theo vai trò
- Where: `prototype/shared/guide.js` · guide item `id:'mobile-finance'`
- Change: wording only — the steps "Flutter: chọn không gian ở header…" / "Flutter Care → Hồ sơ…" / "Flutter CRM là bản mẫu…" now say "App mobile…" ("chọn không gian ở thanh trên"); the Flutter template is no longer the mobile app.
- Canvas target: F16 (Hướng dẫn) only if it shows this guide item; otherwise none
- Logged by: Copilot

## Done

The skill moves entries from "Pending" down here with their result, then updates **Sync baseline** to the commit it compared against. Keep about the 20 most recent entries; older ones are in git history.

### 2026-09-23 · full sync · baseline
- Dumped all of Clinic Web, Patient 360, Patient Mobile and Finance; compared against the 55-screen canvas.
- Result: added I1–I13, J1–J11, K1–K3 (82-screen canvas), pushed to claude.ai/design. Mapping table in `references/coverage.md`.
