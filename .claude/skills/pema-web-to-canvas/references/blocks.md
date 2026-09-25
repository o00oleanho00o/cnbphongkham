# Block của canvas `Pema App.dc.html`

Mọi màn được khai báo bằng dữ liệu trong `class Component … build()` (thẻ `<script type="text/x-dc">`). Template HTML phía trên đã có sẵn cách vẽ từng block, nên **màn mới chỉ cần thêm dữ liệu, không sửa template**. Mỗi block tương ứng một widget/helper trong `flutter-template/lib/`, vì vậy màn dựng bằng các block này luôn làm được trong Flutter.

## Tạo màn

| Helper | Dùng khi | Ghi chú |
|---|---|---|
| `home(id, name, note, role, navKey, tabIndex, blocks, o?)` | Màn tab chính: logo `pema`, nút đổi vai trò, bottom nav | `role`: `'Clinic' \| 'Bác sĩ' \| 'CSKH' \| 'Kế toán' \| 'Care'`; `navKey`: `owner \| staff \| care \| fin` |
| `det(id, title, note, blocks, o?)` | Màn con (`Detail(route)`): nút back + tiêu đề | Dùng cho hầu hết màn chuyển từ web |
| `fin(id, name, note, tabIndex, blocks, o?)` | Màn tài chính (`FinanceScreen`) | Tự thêm dòng vai trò + kỳ báo cáo |

`o` (tùy chọn) có thể có: `hasFab` + `fab: { label }` (icon luôn là `add`), `hasSnack` + `snack: { text, action }`, `hasSheet` + `sheet`, `hasDialog` + `dialog: { title, value }`, `title` (tiêu đề thanh trên khi khác `name`), `ts`/`tw` (cỡ/độ đậm tiêu đề).

`note` hiện dưới tên màn trên canvas. Với màn lấy từ web, mở đầu bằng `WEB + '<route/tab/modal> · <điểm khác biệt khi chuyển sang mobile>'` (`const WEB = 'Web › '`).

## Block nội dung

| Helper | Vẽ ra | Flutter |
|---|---|---|
| `h(title, sub)` | Heading 25/700 navy + dòng phụ | `heading()` |
| `h2(title, sub)` | Heading 26/700 ink (CSKH) | `CareQueue` header |
| `s(title)` | Tiêu đề mục 17/700 | `section()` |
| `hero(title, sub, icon)` | Khối gradient navy→blue, icon mờ lớn; `title` nhận `\n` | `hero()` |
| `m([value, label], …)` | Ô số liệu; **tối đa 3 ô, giá trị ngắn** (≤ 5 ký tự, vd `11,3tr`) | `metric()` |
| `a([label, icon], …)` | Hàng lối tắt icon (3 ô) | `action()` |
| `t(title, sub, icon, tap = true)` | Tile có avatar icon; `sub` nhận `\n`; `tap=false` bỏ chevron | `tile()` |
| `n(text)` | Notice nền `#E8F4FB`, chữ navy; nhận `\n` | `notice()` |
| `p(text, on = true)` | Nút chính 52px; `on=false` là nút bị khóa | `primary()` / `FilledButton` |
| `outlined(text, icon)` | Nút viền 48px | `OutlinedButton.icon` |
| `textBtn(text, icon)` | Nút chữ | `TextButton.icon` |
| `input({ label, value, hint, prefix, lines })` | Ô nhập; có `value` thì nhãn nổi lên viền | `TextField` |
| `search(hint?)` | Ô tìm kiếm có icon | `PatientSearch` |
| `dd(value, label?)` | Dropdown 56px | `DropdownButtonFormField` |
| `dateBtn(text)` | Nút chọn ngày | `showDatePicker` trigger |
| `week()` | Dải 7 ngày, T3 22 đang chọn | `WeekStrip` |
| `chips([[label, state], …])` | Chip; state `'sel' \| '' \| 'dis'` | `ChoiceChip` |
| `check(label, on)` | Dòng checkbox | `CheckboxListTile` |
| `{ photos: true, items: [{ label }, …] }` | 2 ô ảnh minh họa (`photos()` = Trước / Gần nhất) | ảnh placeholder |
| `order(name, qty, route, usage)` | Dòng kiểm tra đơn | order review row |
| `a5(kind, items, footer)` | Bản xem phiếu A5 | A5 preview |
| `txt(text, { s, c, w, ws })` | Đoạn chữ tự do (cỡ, màu, độ đậm, white-space) | `Text` |
| `sp(h)` | Khoảng trống cao `h` px | `SizedBox` |
| `buckets(active)` / `careSearch(active)` / `chip(label)` / `listHead(title, count)` / `careRow(person)` / `empty(text)` | Bộ block hàng chờ CSKH | `features/customer_care/presentation/widgets/care_queue.dart` |
| `finHero(over, value, sub?)` / `pill(text, icon?)` / `mcard(title, sub)` | Block tài chính | `finance.dart` |
| `fc(...items)` | Thẻ viền; bên trong dùng `ftitle(text)`, `fl(label, value)`, `txt(...)`, `fb(...labels)` (nút chữ), `ff(label)` (nút đặc), `fi(text)` (dòng icon tiền), `sp(h)` | `Card` + `Row` |

## Sheet (bottom sheet)

`sheet` là object phẳng, xem mẫu `accountSheet`, `groupSheet`, `paySheet`, `methodSheet`:

```js
{ pad: '0 20px 16px', align: 'stretch', title, ts: 22, tc: '#17324D', g1: 4, sub, ss: 14, sc: MUTED, g2: 12,
  rowPad: '0 8px', rs: 16, rows: [{ icon, is: 21, ic, text, tc, hasTrail: false, trail: '' }],
  hasNotice: true, notice: '…', hasPrimary: true, primary: 'Nút chính' }
```

Sheet chỉ có danh sách dòng + notice + một nút. Form nhiều ô nhập phải làm thành màn `det(...)`.

## Giới hạn cần nhớ

- Khung 390×844 cắt phần tràn (`overflow:hidden`), giống màn đang cuộn. Nên để hành động chính trong khoảng 700px đầu.
- Loại block mới cần cả template HTML lẫn key trong `KEYS` (hoặc `CH` nếu nằm trong `fc`). Chỉ thêm khi không block nào diễn đạt được, và phải có widget Flutter tương ứng.
- Nhóm mới: thêm `{ code, title, sub, screens }` vào `groups`, và thêm `"<code> · <tên>"` vào `options` của prop `group` trong `data-props` (chuỗi đã escape `&quot;`).
- Dữ liệu mẫu dùng `people`, `pt`, `GROUPS`, `money()` trong file (Nguyễn Thu Hà · P001 · BS. Tâm · 10:30 22/9/2026). Không chép tên/dữ liệu từ web (web dùng bộ hồ sơ khác).
- Tên icon là Material Symbols Outlined (vd `photo_camera`, `event`, `task_alt`, `edit_calendar`, `no_photography`). Tên sai sẽ hiện thành chữ.
