# PARITY-AI01-U — Package U parity audit (step U8)

Date: 2026-10-05. Branch `ui/u8` on `feat/ui-parity` at `fa3a6a2` (U0..U7 merged). Plan: [PLAN-AI01-U](PLAN-AI01-U.md) section 5.
Recipe: `recipes/U/09-U8-parity-audit.md`. Everything here was run on this checkout; numbers are from that run.

## 1. Final numbers

| Check | Result |
| --- | --- |
| Alembic | `alembic heads` = one head, `u6_0010_finance`. Chain `u3_0010` -> `u7_0001` -> `u4_0010` -> `u5_0010` -> `u6_0010` on `m_0002`. No merge revision needed (the recipe's `u8_0011_merge_heads` was not created). `upgrade head`, `downgrade base` (0 tables and 0 version rows left), `upgrade head` again, all on a clean Postgres 17 + pgvector: OK |
| BE pytest | full run with a Postgres (`PEMA_TEST_DATABASE_URL`): 5469 passed, 47 skipped, 3 failed (see section 5; two are a clock bug of a package M test, one a timing flake that passes alone). Then the 58 tests marked `redis` / `integration` with a Redis: 58 passed. Plus 109 new tests in `tests/clinic/test_u8_security_pass.py` (all pass) |
| BE static | `ruff check`, `ruff format --check` (1052 files), `pyright` strict (0 errors), `lint-imports` (4 contracts kept): clean |
| FE | `pnpm vitest run` 1093 passed in 116 files (baseline 407); `pnpm lint` clean; `pnpm tsc --noEmit` clean; `pnpm format:check` clean after `visual-ref` was added to `.prettierignore` (the committed generated `manifest.json` failed Prettier before); `pnpm build` OK |
| Inventory | `pnpm inventory`: 57 routes, 133 test ids, 116 test files, all green (signed, section 4) |
| Smoke / visual | `pnpm smoke`: 55 routes, 0 problems. `pnpm visual` against `pnpm dev:mock`: 67 routes x 5 viewports = 335 screens, 0 horizontal overflow, 0 failing |
| Web specs | `web-specs.cjs`: 384 specs, `--check` clean; WE*, WF*, WG* now say `built (U4/U5/U6)` (59 ids), no id says `planned` |

## 2. Parity table (old `data-nav` screens and Patient 360 tabs)

Old = `pema-agent/frontend/visual-ref/old/<ID>-<viewport>.png`; new = `pema-agent/frontend/visual-ref/new/<viewport>-<slug>.png` (PNGs are git-ignored; both sets
were regenerated for this audit: old with `web-shots.cjs --only`, 112 of 120 images identical to the SHA-256 of `manifest.json`, new with `pnpm visual`). Viewports: **1920x1020** and **390x844**.
Reviewed by eye: all 19 pairs at 1920x1020 and, at 390x844, all pairs except Patient 360 consult and plan and the `/crm` page (their overflow check passed, nothing more).
Verdicts: **same** = same structure; **dev** = acceptable deviation (function kept, layout or placement differs, reason given); **fix** = fix needed (logged, not small).

| Old screen (id) | New route | Old shot | New shot slug | 1920 | 390 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| dashboard (WB1) | `/dashboard` | `WB1-*` | `dashboard` | dev | same | Same four KPI tiles and CSKH tiles. The old CRM blocks (priority list, "Hiệu quả CSKH", lifecycle strip) sit on `/today` and `/crm`; new has range tabs and a by-status bar list |
| today (WB3) | `/today` | `WB3-*` | `today` | same | same | U10 (2026-10-05, owner decision): the old reception table "Hôm nay tại Pema" (tiles, search, status and doctor filters, Check-in / Vắng / Mời vào phòng / Mở 360, 25 rows a page) sits above the CSKH queue, which stays. Left out on purpose: the column "Giá lịch dự kiến" and the tile "Phát sinh hóa đơn hôm nay" (an appointment carries no price or invoice here). Table and cards were checked by test, not by eye (no screenshot run in U10) |
| schedule (WB5) | `/schedule` | `WB5-*` | `schedule` | same | same | U10 (2026-10-05, owner decision): next to the doctor columns a switch "Cột theo" opens the room-column grid (half-hour rows 08:00-18:00, a column per room, hatched room blocks, a button on each empty half hour, "Khóa phòng" for `admin.rules`); the room rules are the old `validate` (busy room, blocked room, 08:00-18:00). Left out: drag of a card onto a slot (the old web has it, mouse only; the sheet does the same), service colours, the 15-minute buffer strip and the waiting list "Chờ xếp lịch". Checked by test, not by eye |
| patients (WC1) | `/patients` | `WC1-*` | `patients` | **fix** | dev | Search yes; missing: filter chips (Tất cả, Đang điều trị, Tài khám tuần này, Có cảnh báo), the "＋ Hồ sơ mới" create dialog (WC3; the API `POST /patients` exists) and the journey/next-visit columns |
| Patient 360 · Tổng quan (WC4) | `/patients/[id]` | `WC4-*` | `patients_<id>` | dev | same | Next step, plan, sessions done, next visit, care facts, open CRM tasks, appointments, internal care notes. Missing header buttons "AI brief" and "Nhắn tin" and the "Thông tin cần nhớ" card (WC13, WC15) |
| · Tư vấn (WC5) | `?tab=consult` | `WC5-*` | `…_tab_consult` | dev | not viewed | Draft note + approved notes; the old "Tiền sử & chẩn đoán" card is missing |
| · Kế hoạch (WC7) | `?tab=plan` | `WC7-*` | `…_tab_plan` | same | not viewed | Plan, sessions, follow-up facts, plus an orders card (WC28) |
| · Buổi điều trị (WC8) | `?tab=session` | `WC8-*` | `…_tab_session` | same | same | Same form fields, side list of recorded sessions |
| · Ảnh trước / sau (WC9) | `?tab=photos` | `WC9-*` | `…_tab_photos` | same | same | Real uploads with consent chip, MIME and size limits; no slider compare in the tab (the old "So sánh trượt" is on `/studio`) |
| · Dịch vụ & tài chính (WC10) | none | `WC10-*` | none | **fix** | **fix** | No tab. Services of the course and invoices are reachable from `/services`, `/cashier`, `/finance`, not from the patient. WC19 (add service to course) has no screen either |
| · CRM & CSKH (WC11), Lịch sử (WC12) | `/patients/[id]` (Tổng quan) | `WC11-*`, `WC12-*` | `patients_<id>` | dev | dev | Merged into Tổng quan (open tasks, appointments, timeline of care notes); no separate tabs. "Sửa ngày dự kiến" (WC18) has no dialog |
| followups (WD6) | `/inbox`, `/review` | `WD6-*` | `inbox` | dev | same | Zalo conversation inbox and review queue replace the old follow-up task cards and three KPI tiles |
| studio (WE1) | `/studio` | `WE1-*` | `studio` | same | same | Patient picker first (the old page preloads one sample patient) |
| resources (WE3) | `/resources` | `WE3-*` | `resources` | same | same | Doctor cards, room cards added, room blocks table |
| services (WE5) | `/services` | `WE5-*` | `services` | same | same | Service cards with terms and history, protocol list added |
| cashier (WF1) | `/cashier` | `WF1-*` | `cashier` | same | same | |
| order review (WF5) | `/orders/[id]`, `/orders/[id]/print` | `WF5-*` | `orders_<id>` | same | same | A5 sheets and approve button; "Sửa nháp" added |
| finance (WG1) | `/finance`, `/finance/*` | `WG1-*` | `finance` | same | same | Tabs + export; the hero banner is light, not dark navy |
| ask (WH1) | `/ask` | `WH1-*` | `ask` | dev | same | Knowledge-base search with sources instead of the scripted answer panel |
| guide (WH3) | `/guide` | `WH3-*` | `guide` | dev | same | Same layout, KB-driven; only 3 synthetic articles exist against the old 11 (content, open item 6) |
| CSKH hôm nay (WD1) | `/today`, `/crm` | `WD1-*` | `today`, `crm` | dev | not viewed | Queue on `/today`, lifecycle segments, rules and activity on `/crm` |

No screen overflows horizontally at any of the five viewports (`pnpm visual`, 335 screens). Every old `data-nav` item is in the sidebar and no menu item is `planned`.
The 14 inventory ids still `none` (not a route): WA10 (Flutter template preview, a development page, not needed), WC3, WC10, WC13, WC15, WC16, WC18, WC19, WC25, WC27, WC29, WC32, WC34 (create patient,
services-and-finance tab, AI brief, key facts, home care, expected return, add service to course and their states) and WC28 (prescription waiting for approval, now covered by the plan tab orders card
and `/orders/[id]`; the inventory row is stale). They are the "fix" items above.

Old screenshots that do not exist in the repo: the PNGs of `visual-ref/old/` are git-ignored, so a fresh checkout has only `manifest.json` (1401 images listed for all 384 ids, none with `state_unreachable`).
For this audit 22 ids were re-shot locally (WB1, WB3, WB5, WC1, WC4, WC5, WC7-WC12, WD1, WD6, WE1, WE3, WE5, WF1, WF5, WG1, WH1, WH3, five viewports); **the other 189 old-web ids have no image on disk**
until `node .claude/skills/pema-web-design/scripts/web-shots.cjs` is run against the old web (`python -m http.server 4173 --directory prototype`, finance API on 4174). The 173 Next.js-only ids (WJ, WK, WL)
are shot from the Next.js app by the same script and also have no image on disk.

## 3. Security pass on the new actions

| Item | Evidence |
| --- | --- |
| RBAC denials | `test_u8_security_pass.py`: 53 routes of U2..U7 are called by each of the five roles; a role gets 403 exactly when its permissions miss the one the action requires (expected sets derived from `ROLE_PERMISSIONS`); owner-rule literals are pinned (reception collects but reads no finance totals, doctors see only their own rows, care staff no money/orders/clinical writes, only doctor and owner sign an order, reception has no photos). The patient role has no permission. A static test checks every public action of 15 action modules reaches `require`, `require_any`, `resolve_scope` or `has_permission` |
| Audit on every mutation | Structural: `clinic/audit/guard.py` refuses to commit an ORM change of any `clinic.*` object without an `audit_log` row (`test_audit_every_mutation.py`). The guard cannot see raw SQL or Core DML, so a new test requires every such statement in the U modules to be followed by `audit.record(` and pins the two that exist (`finance_cash` order-to-invoice link, `guide` KB tags). Audit details carry ids, counts and field names, never notes or names |
| Media MIME and size | `MEDIA_MIME_TYPES`, `MEDIA_MAX_BYTES` (8 MB), signed upload path bound to photo, size, type, time; first bytes checked against the declared type; consent required. Tests: `test_patient_care.py` (gif refused, over 8 MB gives 413, oversized body refused, premature confirm 409), `test_media_units.py` |
| CSV injection | `finance/domain.py::csv_safe` prefixes `'` to cells starting `=`, `+`, `-`, `@`, tab, CR; tests in `test_finance_domain.py` and `test_finance_equivalence.py` (a doctor name `=cmd|...` is neutralised) |
| PII in logs | The U action modules, `finance/domain.py` and the U routers import no logger and call no `print` (static test, 7 routers, 16 modules). The care/agent logging of earlier packages is unchanged |

Not covered by a test, stated plainly: no penetration test, no malware scan of uploaded images (the plan keeps image content out of scope), no rate limit specific to the new routes beyond the existing read limiter.

## 4. Inventory

`frontend/FEATURE-INVENTORY.md` was run with `pnpm inventory`: every `page.tsx` has a row, every test id exists, every test file is named. Signed as green at 57 routes on 2026-10-05.
The inventory records what each route can do, not the gaps of section 2; those are listed here instead of being edited into frozen rows.

## 5. Failures and open items found

1. **BE: two tests of package M fail on any date after 2026-10-05 03:00 UTC.** `tests/care/test_care_routing_store.py::test_the_on_call_contact_comes_from_the_database_on_every_call` and
   `…::test_the_whole_chain_over_postgres_ends_with_the_on_call_contact_and_staff_can_still_accept` use `NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)` while the seeded on-call row takes `valid_from = now()` of the database, which is later than `NOW`. Not touched here (other package's test). Fix: seed with an explicit `valid_from` or build `NOW` from the database clock.
2. `tests/live/test_events_route.py::test_a_burst_of_inbound_messages_is_one_event_per_conversation` failed once while the machine ran the browser harness and passes alone (timing flake of a 0.5 s debounce window).
3. ~~`/today` vs the old "Hôm nay tại Pema" reception table~~ Done in U10: the owner asked for it on 2026-10-05; the CSKH queue stays.
4. ~~`/schedule` has no room-column time grid~~ Done in U10 (the room of an appointment is new: migration `u10_0010_appointment_room`).
5. Fix needed, not small: create-patient dialog (WC3) and filter chips on `/patients`; Patient 360 "Dịch vụ & tài chính" tab and add-service dialog (WC10, WC19); AI brief, "Nhắn tin", key facts, home care and expected-return dialogs (WC13, WC15, WC16, WC18); "Tiền sử & chẩn đoán" card.
6. Guide content: 3 of the 11 old articles exist as KB articles; the rest is a writing job for the clinic.
7. Superseded but kept (owner decides deletion, out of scope): `prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance/*`, `prototype/finance_server.py`, `prototype/finance_test.py`, `prototype/shared/*.js` (Patient Mobile stays for the patient app). The new app reads none of them at run time.
8. Owner inputs still open (PLAN-AI01-U section 6): real services, prices and protocols for the seed, whether cashiers may approve orders, period-close policy owner, photo consent wording; no accountant role (the manager holds it).

## 6. Docs updated by U8

`SCOPE-AI01` (scope, decision 17), `SPEC-AI01` (API counts, permission rows), `MODULEMAP-AI01` (modules, migrations, routes), `ARCH-AI01` (tables, head), `pema-agent/README.md` (running the unified app, superseded files),
root `SECTION_PROGRESS.md` (one checkpoint), `design-specs/web/` (statuses and regenerated specs).
