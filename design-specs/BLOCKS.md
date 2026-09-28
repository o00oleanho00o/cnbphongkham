<!-- Sinh tự động — xem README.md -->
# Canvas block → Compose

Helper trong `build()` của `Pema App.dc.html` và component tương ứng (`pema-kmp/core/ui/.../widgets`). Màu/chữ: chỉ `PemaColors.*`, `PemaType.*`; icon `PemaIcon("material_name", filled)`.

| Canvas | Khóa block | Compose |
|---|---|---|
| `h(title, sub)` | heading | PemaHeading(title, sub) |
| `h2(title, sub)` | h2 | PemaH2(title, sub) |
| `s(title)` | section | PemaSection(title) |
| `hero(title, sub, icon)` | hero | PemaHero(title, sub, icon) — kicker "PEMA • CHĂM SÓC LIÊN TỤC" |
| `m([v, l], …)` | metrics | PemaMetrics(v to l, …) — các ô cao bằng nhau |
| `a([label, icon], …)` | actions | PemaActions(listOf(PemaAction(label, icon) {…})) |
| `t(title, sub, icon, tap)` | tile | PemaTile(title, sub, icon, onClick | null) |
| `n(text)` | notice | PemaNotice(text) |
| `p(text, on)` | primary | PemaPrimary(text, onClick | null) |
| `outlined(text, icon)` | outlined | PemaOutlinedButton(text, icon = …) |
| `textBtn(text, icon)` | textBtn | PemaTextButton(text, icon = …) |
| `dateBtn(text)` | dateBtn | PemaTextButton(text, icon = "calendar_month", iconFilled = true) |
| `input({label, value, lines})` | input | PemaTextField(value, label, minLines) |
| `search(hint)` | input+prefix | PemaSearchField(value, hint) |
| `dd(value, label)` | dd | PemaDropdownField(value, options, label) |
| `week()` | week | WeekStrip() (days/selected/onSelect khi cần chọn ngày) |
| `chips([[label, sel|dis]])` | chips | PemaChipWrap { PemaFilterChip(label, selected, enabled) } |
| `check(label, on)` | check | PemaCheckRow(label, checked) |
| `photos()` | photos | Ô ảnh 220dp bo 18 nền Tint + icon face 76dp (ảnh thật: LocalPhoto) |
| `txt(text, {s, c, w})` | txt | PemaText(text, size, color, weight) |
| `sp(h)` | sp | Spacer(h.dp) |
| `fc(…)` | fcard | PemaInfoCard { … } |
| `ftitle(text)` | ftitle | PemaCardTitle(text) |
| `fl(label, value)` | fline | PemaCardLine(label, value) |
| `fb(text, …)` | btns | PemaCardTextButtons(text to {…}, …) |
| `ff(text)` | filled | PemaCardFilledButton(text) {…} |
| `careRow(p)` | careRow | PemaCareRow(initials, name, group, meta) {…} |
| `chip(label)` | inputChip | PemaInputChip(label) {…} |
| `empty(text)` | empty | PemaEmpty(text) |
| `pill(text, icon)` | pill | PemaPillButton(text, icon) |
| `buckets / careSearch / listHead` | … | feature:care CareQueue (bucket, search row, list header) |
| `order / a5` | … | feature:orders OrderLineCard / phiếu A5 |
| `period / finHero / mcard` | … | feature:finance PeriodRow / FinanceHero / MaterialRateCard |
| `home(…)` | appMain | PemaScaffold + PemaMainTopBar(role, bell) + PemaBottomNav (tab theo vai trò) |
| `det(…)` | appDetail | DetailScaffold(title = Routes.appBarTitleOf(Routes.X)) |
| `{hasFab}` | fab | DetailScaffold(floatingActionButton = { PemaExtendedFab(label) }) |
| `{hasSheet}` | sheet | PemaBottomSheet { … } (không lồng verticalScroll) |
| `{hasSnack}` | snack | rememberPemaMessenger().show(text) / PemaSnackbar |
| `{hasDialog}` | dialog | PemaDialog(title) { … } |
