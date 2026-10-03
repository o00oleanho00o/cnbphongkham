# FEATURE-INVENTORY

Frozen at package U step U1 (2026-10-03), before any style was touched. Rule of package U (PLAN-AI01-U section 2,
principle 2): **no feature loss**. Later steps (U2..U7) only APPEND rows for the routes they add; nobody removes or
rewords a capability of an existing row without an owner decision. U8 signs the whole file.

How it is checked: `pnpm inventory` (`scripts/inventory-check.ts`) fails when

- a route in the table has no `page.tsx`, or a `page.tsx` has no row (so a new screen must append its row);
- a test id in the table no longer exists (file missing, or the `::title` is no longer an `it`/`test`/`describe` title there);
- a test file under `src/` or `mock/` is not named anywhere in this file (a test cannot disappear unnoticed).

Test id syntax: the path of a test file in backticks (the whole file), or the path, two colons and the title in backticks
(one `it`, `test` or `describe`). Permissions are the ones of `lib/nav.tsx` and the pages (a convenience; the backend decides).

## Routes

| Route | Screen | Capabilities | Test ids | Owner |
| --- | --- | --- | --- | --- |
| `/` | Redirect | goes to `/today` (the shell then lands the role on its own home, `homeFor`) | `src/lib/nav.test.ts::homeFor` | U1 |
| `/login` | Sign-in | e-mail and password; `next` target after sign-in; backend sentence on a wrong password or 429; already signed in goes on | `mock/auth-login.test.ts` | U1 |
| `/today` | Việc hôm nay | list CRM tasks due by calendar date; status chips (open, rescheduled, resolved); channel chips (all, call, zalo, sms); care-group select; "Của tôi" toggle; copy the message to send; live refresh on `tasks.changed`; mark done; record result; open the resolve sheet (channel, outcome, note, booking date and duration, next date, owner box, priority); marketing opt-out badge; link to Patient 360 | `src/app/(admin)/today/page.test.tsx`; `src/components/ops/today/resolve-task-sheet.test.tsx`; `src/lib/ops/crm-task-view.test.ts`; `src/lib/ops/assignee-options.test.ts` | U1 |
| `/dashboard` | Tổng quan | range chips (today, this week, this month); appointment tiles (visits in the range, arrived and waiting, missed with cancelled, patients seen with new and returning); care tiles when the role reads tasks (due, follow-up completion, overdue with patients, contact rate, booked after care); breakdown of appointments by status; a dash for a rate with nothing to divide by; no revenue and no invented number; a doctor sees own visits only and is told so; live refresh on `appointments.changed` and `tasks.changed`; link to the schedule and to "Việc hôm nay" | `src/app/(admin)/dashboard/page.test.tsx`; `src/lib/ops/dashboard-view.test.ts`; `mock/schedule.test.ts::dashboard KPIs (mock)` | U2 |
| `/schedule` | Điều phối lịch | day and 7-day board; date picker, previous and next, "Hôm nay"; doctor filter (none for a doctor: own board); status chips with counts (Đặt hẹn, Đã xác nhận, Đang chờ, Đang điều trị, Hoàn tất, Vắng hẹn, Đã hủy) and "Hiện lịch hủy / vắng"; tiles (visits, treatment minutes, waiting, closed); doctor columns on a wide screen, one list on a phone; one quick button per visit (Check-in, Bắt đầu điều trị, Hoàn tất); sheet: book (patient, doctor, date, time, duration, note), "Tìm giờ trống", reschedule a booked or confirmed visit, confirm, miss, cancel with a reason, link to Patient 360; the backend's sentence for hours, break and double booking; stale version asks for a reload; live refresh on `appointments.changed`; book and confirm need `appointment.write`, the visit steps `appointment.check_in` | `src/app/(admin)/schedule/page.test.tsx`; `src/components/ops/schedule/appointment-sheet.test.tsx`; `src/lib/ops/schedule-view.test.ts`; `mock/schedule.test.ts::schedule board (mock)`; `mock/schedule.test.ts::reception transitions (mock)`; `mock/schedule.test.ts::booking rules (mock)` | U2 |
| `/inbox` | Inbox | conversation list with search (name, patient code, content) and status chips; unread count; viewers line; master-detail (child screen on a phone); thread: messages, send reply, mark read, status box, assignment box (Tôi, Giữ nguyên, Chưa giao, colleagues), "Nhận xử lý"; pending-draft count; live refresh (`inbox.changed`, `presence.changed`) with 30 s fallback; presence beat every 15 s | `src/app/(admin)/inbox/page.test.tsx`; `src/components/ops/assignee-status.test.tsx`; `src/lib/live/use-live-events.test.tsx`; `src/lib/live/use-presence-heartbeat.test.tsx`; `src/lib/ops/presence-view.test.ts` | U1 |
| `/review` | Hàng đợi duyệt AI | queue with status chips (pending, escalated, approved, rejected), kind select and "Cần bác sĩ" toggle; selection kept in `?i=`; live refresh on `review.changed`; detail: draft, cited sources, decision; edit then approve (blocked when the item changed meanwhile); reject with reason; escalate; doctor-only items blocked without `review.decide_clinical` | `src/lib/live/live-connection.test.ts` | U1 |
| `/patients` | Hồ sơ bệnh nhân | search by name or code (`?q=` from the top bar); list with avatar, status badges; open Patient 360 | `src/lib/ops/format.test.ts` | U1 |
| `/patients/[id]` | Patient 360 | sections Thông tin, Chăm sóc sau điều trị (last visit, next due, overdue days, sessions left), open care tasks, Lịch hẹn, Liệu trình with progress, Ghi nhận chăm sóc, Hội thoại, Đồng ý của khách, Dòng thời gian; section tabs; link to the care agent timeline with `care.read`; read only | `src/lib/ops/format.test.ts` | U1 |
| `/templates` | Tin nhắn mẫu đã duyệt | list of approved templates; create and edit (code, title, body with 0/max counter, marketing flag) with `kb.manage`; approve with `review.decide_clinical` | `src/lib/ops/clipboard.test.ts` | U1 |
| `/care/handoffs` | Yêu cầu đang chờ tôi | handoff cards (reason, summary, SLA, on-call step badge); Nhận (opens the timeline); Từ chối needs a reason and may suggest a colleague; backend refusal shown on the card and list reloads; scope chip "all open rounds"; live refresh on `handoff.changed`; buttons only as `can_accept` allows | `src/app/(admin)/care/handoffs/page.test.tsx`; `mock/care.test.ts`; `src/lib/care/sla.test.ts`; `src/lib/care/labels.test.ts` | U1 |
| `/care/patients/[id]` | Redirect | opens the timeline | none (redirect only) | U1 |
| `/care/patients/[id]/timeline` | Care agent timeline | state (who holds, since, autonomy now and base, lowered level, paused); why the agent asked for a person; drafts waiting for review; paused reminders; what the agent did; what it remembers; refresh on `care.changed` | `src/lib/care/labels.test.ts` | U1 |
| `/care/patients/[id]/release` | Return the conversation | note, optional LOWER level for N days, consequence in the backend words, confirm; note instead of a form when the caller does not hold the conversation | `src/components/care/release-form.test.tsx`; `src/lib/care/forms.test.ts` | U1 |
| `/care/patients/[id]/tell-agent` | Tell the agent | free text saved as care memory (source `staff`); list of saved instructions | `src/lib/care/forms.test.ts` | U1 |
| `/admin/care` | Redirect | opens `/admin/care/staff` | none (redirect only) | U1 |
| `/admin/care/staff` | Care staff | skills, weekly shifts, capacity, language per person (sheet) | `src/lib/care/forms.test.ts` | U1 |
| `/admin/care/on-call` | 24/24 on-call contact | add and edit the on-call Zalo number, owner, valid from and to, on or off | `src/lib/care/forms.test.ts` | U1 |
| `/admin/care/matrix` | Depth and autonomy matrix | thresholds per signal, post-procedure window, repeat count, unverified-customer ceiling, auto-send rules per action type (L2 after N, D3 open), save with the version read, pending badge and approve by doctor, manager or owner, read only when the backend says so | `src/app/(admin)/admin/care/matrix/page.test.tsx`; `src/lib/care/matrix-draft.test.ts` | U1 |
| `/admin/care/timing` | SLA and time windows | reply SLA, after-hours depth, send window; save | `src/lib/care/forms.test.ts` | U1 |
| `/admin/care/alerts` | Agent alerts | list of care alerts, empty state, live status | none | U1 |
| `/admin/users` | Nhân viên | list with role, status, last sign-in; filters (search, role, status) sent to the list; add, edit name and role, lock and unlock (signs the person out, versioned), reset password; own account has no lock or reset; owner only manages, manager only lists; 409 and 429 sentences | `src/app/(admin)/admin/users/page.test.tsx`; `mock/admin-users.test.ts`; `mock/admin-users-password.test.ts`; `src/lib/ops/staff-view.test.ts` | U1 |
| `/admin/auth` | Tài khoản của tôi | change own password (current, new, minimum 8 characters) | `mock/auth-password.test.ts` | U1 |
| `/admin/overview` | Tổng quan AI | system health tiles (bot state, data kept, uptime), LLM usage bar chart over N days, "LLM not configured" banner linking to providers | none | U1 |
| `/admin/threads` | Phiên chat AI | list of AI sessions (filter by account), bot on or off per session, delete a session, open the session drawer with the trace | `src/lib/admin/traces/trace-types.test.ts` | U1 |
| `/admin/contacts` | Danh bạ | collected contacts filtered by account, delete a contact | none | U1 |
| `/admin/friends` | Bạn bè | friend requests (accept, reject) and friend list for a running personal account | none | U1 |
| `/admin/schedules` | Lịch hẹn của bot | list jobs by account, edit drawer, enable or disable, run now, delete, run history drawer, timezone | none | U1 |
| `/admin/memory` | Trí nhớ | facts the assistant saved, per account, delete a fact | none | U1 |
| `/admin/kb` | Kho tri thức | list sources with search and paging, add source (file or text, size guard), reindex, approve (`kb.manage`), view chunks, search the store, assign agents, delete with warning, how-to modal, poll while processing | `src/lib/admin/kb/kb-poll-loop.test.ts`; `src/lib/admin/kb/kb-upload-size-guard.test.ts`; `src/lib/admin/kb/kb-page-clamp.test.ts` | U1 |
| `/admin/accounts` | Tài khoản Zalo | list, enable or disable, edit drawer (display name, agent, policies, allowlist, group behaviour), QR login, delete, channel settings panel, policy profile badge | `src/lib/admin/accounts/mo-ta-loai-kenh.test.ts`; `src/lib/admin/channels/channel-draft.test.ts` | U1 |
| `/admin/agents` | Agents | agent cards, create modal, delete, provider hint | `src/lib/admin/agents/agent-draft.test.ts` | U1 |
| `/admin/agents/new` | New agent | identity, model, tools, KB sources, policy profile; create or cancel; unsaved-changes guard | `src/lib/admin/shared/unsaved-changes-guard.test.ts` | U1 |
| `/admin/agents/[id]` | Agent detail | same sections, save with dirty check, not-found state | `src/lib/admin/agents/agent-draft.test.ts` | U1 |
| `/admin/tools` | Tools | per account tool toggles, image generation, vision, web search and fetch chain settings modals, usable hints | none | U1 |
| `/admin/mcp` | MCP | server list, add and edit form, enable, assign agents, re-approve tool set, delete | `src/lib/admin/mcp/mcp-status-label.test.ts` | U1 |
| `/admin/traces` | Trace agent | list of turns with paging, step cards (model output, tool calls with parameters) | `src/lib/admin/traces/trace-types.test.ts` | U1 |
| `/admin/logs` | Logs | app log lines with level filter, audit log table | none | U1 |
| `/admin/policy` | Hồ sơ chính sách | profiles, set the profile of an account or agent, pending identity links and confirm | `src/lib/admin/policy/policy-text.test.ts`; `src/lib/admin/accounts/policy-profile-text.test.ts` | U1 |
| `/admin/tuning` | Mô hình & cấu hình | provider section, tuning groups with search, per-field control with presets, reset one field or all, change password section | `src/lib/admin/tuning/tuning-commit-value.test.ts`; `src/lib/admin/tuning/tuning-number-presets.test.ts`; `src/lib/admin/tuning/tuning-types.test.ts`; `src/lib/admin/model/provider-form-fields.test.ts`; `src/lib/admin/model/llm-base-url-presets.test.ts` | U1 |
| `/admin/tuning/[group]` | Tuning group | same page opened on one group (deep link) | `src/lib/admin/tuning/tuning-types.test.ts` | U1 |
| `/dev/kit` | Kit examples (development only) | all kit components in both themes; a production build answers 404 | `src/ui/kit-examples.test.tsx` | U0 |

## Shell, navigation, permissions

| Area | Capabilities | Test ids | Owner |
| --- | --- | --- | --- |
| Shell | session load from `GET /api/v1/me`, menu filtered by permission, mobile tab bar, top bar search and bell, unsaved-changes guard on every link, dark and light | `src/ui/app-shell.test.tsx`; `src/ui/sidebar.test.tsx`; `src/ui/top-bar.test.tsx`; `src/lib/nav.test.ts` | U0 |
| Proxy | `/api/v1/**` and `/healthz` forwarded, hostile paths refused | `src/lib/server/api-proxy.test.ts` | U1 |
| Live | event stream, reconnect, coalescing, fallback refresh | `src/lib/live/live-types.test.ts`; `src/lib/live/live-connection.test.ts` | U1 |
| Assignable staff | list for the owner boxes, shared for a minute | `src/lib/staff/assignable-staff.test.ts`; `src/lib/staff/use-assignable-staff.test.tsx`; `mock/staff-assignable.test.ts` | U1 |

## Design kit and other tests

| Area | Test ids | Owner |
| --- | --- | --- |
| Kit | `src/ui/badge.test.tsx`; `src/ui/button.test.tsx`; `src/ui/card.test.tsx`; `src/ui/dialog.test.tsx`; `src/ui/empty-state.test.tsx`; `src/ui/field.test.tsx`; `src/ui/tabs.test.tsx`; `src/ui/tile.test.tsx`; `src/ui/tokens.test.ts`; `src/ui/workspace.test.tsx` | U0 |
| Dashboard helpers (ported) | `src/lib/admin/kb/kb-agent-sources-dirty.test.ts`; `src/lib/admin/kb/kb-delete-warning-message.test.ts`; `src/lib/admin/kb/kb-poll-guard.test.ts`; `src/lib/admin/kb/kb-source-name-from-file.test.ts`; `src/lib/admin/shared/backdrop-close-guard.test.ts`; `src/lib/admin/shared/fold-for-search.test.ts`; `src/lib/admin/shared/slugify-vietnamese.test.ts`; `src/lib/admin/shared/so-sanh-phien-ban.test.ts` | U1 |
| Mock backend | `mock/contract.test.ts` | U1 |
| Inventory tooling | `src/lib/inventory.test.ts` | U1 |
