---
name: pema-web-to-canvas
description: Đối chiếu Pema web (Clinic Web, Patient Mobile web, Finance) với design canvas "Pema App.dc.html" của claude.ai/design — bắt đầu từ nhật ký web-changes.md và git diff từ mốc đồng bộ thay vì quét lại toàn bộ — tìm màn/tab/dialog web còn thiếu hoặc đã đổi và dựng bổ sung vào canvas theo mẫu mobile Flutter, kiểm tra render rồi đẩy lên claude.ai/design. Dùng khi được yêu cầu "check web còn thiếu màn nào trong design", "chuyển template web sang design Flutter", "cập nhật canvas theo web". Không viết code .dart.
---

# Web Pema → design canvas Flutter

Canvas `Pema App redesign canvas/Pema App.dc.html` là bản thiết kế mobile của Flutter template, và là nơi bắt đầu thiết kế màn mới. Skill này bổ sung vào canvas các màn web chưa có, **chỉ ở mức thiết kế**. Code Flutter (`flutter-template/lib/`) không đụng tới; nếu cần thì làm riêng theo `AGENT.md` › "Quy tắc riêng cho template Flutter".

Đọc trước: `AGENT.md` (dữ liệu tổng hợp, Patient 360, AI/nháp cần bác sĩ duyệt) và `.agents/skills/pema-design/references/visual-system.md` (màu, chữ, radius Pema).

Đường dẫn script tính từ gốc repo: `S=.claude/skills/pema-web-to-canvas/scripts`. File tạm (dump, ảnh chụp) để ngoài repo (scratchpad hoặc `%TEMP%`), không commit.

## 1. Chuẩn bị

| Cần | Lệnh | Kiểm tra |
|---|---|---|
| Web prototype | `docker compose up -d pema-prototype` | http://127.0.0.1:4173/clinic-web/ |
| Design viewer (dev, hot-swap) | `cd design-viewer && npm run dev` | http://localhost:4180 |
| Playwright + Chromium | `npx -y playwright@latest install chromium` (một lần) | script tự tìm trong npx cache; hoặc đặt `PLAYWRIGHT_MODULE` |

Finance web cần `python prototype/finance_server.py` mới có số liệu. Không có thì dump vẫn liệt kê được 4 tab, và nhóm H của canvas đã phủ phần này.

## 2. Xem web đã đổi gì từ lần đồng bộ trước

**Bắt đầu từ đây, đừng quét cả web.** [web-changes.md](web-changes.md) là nhật ký do người/agent sửa web ghi lại (quy tắc ở `AGENT.md` › "Ghi nhận thay đổi web cho design canvas"). Nó có dòng **Mốc đồng bộ** là commit mà canvas đã khớp web.

```sh
node $S/pending.cjs      # mục "Chờ chuyển" + file web đổi từ mốc, ✗ = đổi mà chưa ai ghi, gợi ý --only
```

- **Không có mục chờ và không có file đổi** → báo "canvas đang khớp web" rồi dừng.
- **Có mục chờ**: đọc từng mục (nơi sửa, thay đổi, canvas dự kiến) và mở đúng các màn canvas đó.
- **File `✗ CHƯA GHI`**: đọc `git diff <mốc> -- <file>` (chỉ file đó) để tự viết mục còn thiếu vào "Chờ chuyển", rồi xử lý như mục bình thường.
- Chỉ dump các màn liên quan, bằng lệnh `--only` mà `pending.cjs` in ra:

```sh
node $S/dump-web.cjs "$TMP/web-dump.txt" --only=clinic:today,dialog:today
node $S/canvas.cjs list | grep -E '^(I2|I4) '           # xem màn canvas tương ứng
```

**Dump toàn bộ** (`dump-web.cjs` không có `--only`, cộng `canvas.cjs list`) chỉ làm khi: nhật ký thiếu mốc; mốc không còn trong git history; đổi token/shell dùng chung (`design.css`, `ui.js`); hoặc người dùng yêu cầu rà lại tất cả.

`dump-web.cjs` tự duyệt mọi `data-nav`, `data-tab`, `data-modal`, `data-screen`, `data-finance-tab`. Dialog mở bằng nút (Đặt lịch, Thu tiền, Xử lý…) và màn mobile chỉ vào được qua một dòng nằm trong màn khác đều khai báo ở đầu script (`CLINIC_DIALOGS`, `MOBILE_LINKS`). Web thêm nút/màn mới thì bổ sung vào hai danh sách này. Dòng `FAILED` trong dump nghĩa là selector/nhãn nút đã đổi: sửa script, đừng bỏ qua. Web thêm file JS mới thì thêm dòng vào bảng `MAP` của `pending.cjs`.

## 3. Tìm phần thiếu

So phần dump (theo mục nhật ký, hoặc toàn bộ) với [references/coverage.md](references/coverage.md) (bảng web → mã màn canvas) và các màn canvas tương ứng:

- **Đã phủ**: canvas có màn cùng mục đích **và** cùng các trường/hành động chính. Chỉ trùng tiêu đề thì chưa đủ; ví dụ C6 là bản rút gọn, nên form CSKH đầy đủ của web vẫn thành I13.
- **Thiếu**: trang, tab, modal hoặc dialog web có hành động hay dữ liệu mà canvas không thể hiện.
- **Bỏ qua**: phần chỉ dành cho desktop (sidebar, bộ chọn tài khoản demo, kéo-thả lịch) và các màn chỉ Flutter có (cuối coverage.md).

Liệt kê cho người dùng: màn web → lý do thiếu → mã canvas dự kiến, rồi làm tiếp. Không cần dừng xin duyệt, trừ khi phạm vi lớn bất thường.

## 4. Dựng màn vào canvas

Thêm dữ liệu trong `build()` của canvas, ngay trước `const groups = [`. Cách dùng block xem ở [references/blocks.md](references/blocks.md).

- **Nhóm**: giữ A–H nguyên vẹn (mirror Flutter). Bổ sung nối tiếp vào I (vận hành Clinic), J (Patient 360), K (Pema Care), đánh số tiếp (I14, J12…). Chỉ mở nhóm mới (L…) cho mảng mới hẳn, nhớ thêm vào `groups` và vào option của prop `group`.
- **Chỉ dùng block có sẵn**, để màn nào cũng dựng được bằng widget Flutter hiện có. Không sửa template HTML, trừ khi thật sự thiếu block (xem blocks.md).
- **Chuyển desktop sang mobile** (theo `pema-design`: màn con, sheet ngắn, không bê bảng desktop):

  | Web | Canvas |
  |---|---|
  | Bảng nhiều cột (tiếp đón, hóa đơn) | `fc(...)` mỗi dòng một thẻ: `ftitle` + `fl` + nút `ff`/`fb` |
  | Lưới phòng × giờ, lịch tuần | `week()` + `dd` chọn phòng + `s(phòng)` + `t(giờ, …)` |
  | Bộ lọc / tab trạng thái | `chips([...])`, mục chọn là `'sel'` |
  | KPI cards | `m(...)` tối đa 3 ô, còn lại dùng `t(...)` |
  | Modal có nhiều ô nhập | màn `det(...)` riêng với `dd`/`input`/`check` + `p(...)` |
  | Lựa chọn ngắn (phương thức, nhóm) | `hasSheet` với `rows` radio |
  | Timeline / lịch sử | chuỗi `t(ngày · sự kiện, người ghi nhận, icon, false)` |

- **Dữ liệu**: dùng `pt`, `people`, `GROUPS`, `money()` của canvas, không chép tên hay số từ web. Giữ các câu ràng buộc nghiệp vụ của web: AI chỉ là nháp, không suy hoàn tất điều trị từ thanh toán, tin nhắn không phải kênh cấp cứu, ảnh minh họa không chấm hiệu quả, CSKH không gửi Zalo/SMS thật.
- **Ghi chú màn** bắt đầu bằng `WEB + '<route/tab/modal> · <điểm khác khi chuyển sang mobile>'` để người duyệt biết nguồn.
- Cập nhật câu giới thiệu trong `<header>` nếu phạm vi nhóm đổi.

## 5. Kiểm tra

```sh
node $S/canvas.cjs check "Pema App.dc.html" I,J,K "$TMP"   # exit 1 nếu có lỗi
```

Đạt khi: `errors` rỗng, `unresolved` rỗng (không còn `{{ }}`), `overflow` rỗng, `total` = số cũ + số màn thêm. Sau đó **mở từng ảnh `canvas-<nhóm>.png` để xem**: chữ tràn, metric vỡ dòng, icon hiện thành chữ (sai tên), FAB/sheet che nội dung quan trọng. Chỉ có exit code 0 thì chưa đủ.

## 6. Đẩy lên claude.ai/design

Project: "Pema App redesign canvas", id `7822035f-ae10-4b1f-a802-ce789b25a393` (project thường, không phải design system). Tool `DesignSync` chỉ dùng trong luồng `/design-sync` do người dùng tự chạy; nếu chưa chạy thì nhắc họ chạy. Trong luồng đó, **chỉ cập nhật đúng file đã sửa**:

1. `DesignSync get_file` file đó. Kết quả lớn sẽ được lưu ra file JSON.
2. `node $S/remote-diff.cjs <file JSON> "Pema App redesign canvas/Pema App.dc.html"`. Dòng `-` là chỉnh sửa chỉ có trên claude.ai/design: phải gộp vào local (hoặc hỏi người dùng) trước khi ghi đè. Không có dòng `-` thì an toàn.
3. `finalize_plan` với `localDir` = thư mục canvas, `writes: ["Pema App.dc.html"]`, `deletes: []`, rồi `write_files` với `localPath`.
4. `get_file` lại và so với file local (bỏ khác biệt CRLF) để xác nhận đã khớp.

Không xóa file remote, không tạo `.design-sync/config.json`, không chạy luồng build design system.

## 7. Kết thúc

- Docker viewer (localhost:4190) đóng gói canvas lúc build: `docker compose up -d --build pema-design-viewer`.
- Cập nhật [references/coverage.md](references/coverage.md) (mốc ngày, tổng số màn, dòng mới).
- Cập nhật [web-changes.md](web-changes.md): chuyển từng mục đã làm từ "Chờ chuyển" xuống đầu "Đã xử lý", thêm dòng `- Kết quả: <mã canvas đã thêm/sửa>, đã/chưa đẩy lên claude.ai/design`. Đổi **Mốc đồng bộ** thành commit web vừa đối chiếu (`git rev-parse --short HEAD`, hoặc commit sẽ tạo ở bước dưới nếu thay đổi web chưa commit). Mục chưa làm được thì để lại ở "Chờ chuyển" kèm lý do. Chạy lại `pending.cjs`: phải báo 0 mục chờ và 0 file `✗`.
- Theo `AGENT.md` với thay đổi chỉ UI: append checkpoint vào `SECTION_PROGRESS.md` (màn đã thêm, viewport 390×844, cách kiểm tra). Không ghi tính năng Flutter đã có chỉ vì canvas đã có màn.
- `git diff --check`, rồi commit file canvas + coverage + web-changes, ví dụ `design: add web-only screens to Pema App canvas`. Không commit dump hay ảnh chụp.
- Báo lại: màn đã thêm theo nhóm, kết quả `check`, đã/chưa đẩy lên claude.ai/design, và phần còn lại (vd `Pema Prototype.dc.html` bản bấm thử chưa có các màn mới).
