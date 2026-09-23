# Nhật ký thay đổi web → design canvas

Mốc đồng bộ: `1564115`

Mỗi lần thêm/sửa/xóa màn, tab, modal, dialog, trường, hành động hay câu ràng buộc nghiệp vụ **hiển thị** trên web Pema (`prototype/clinic-web`, `prototype/patient-mobile`, `prototype/finance`, `prototype/shared/*.js|*.css`), thêm một mục vào **Chờ chuyển**, commit cùng thay đổi web. Skill `pema-web-to-canvas` đọc mục ở đây và chỉ dump/sửa những màn liên quan, không phải quét lại toàn bộ web.

**Cần ghi**: màn/tab/modal/dialog mới hoặc bị xóa · thêm/bớt/đổi trường, nút, bộ lọc, trạng thái · đổi luồng (nút mở màn nào, lưu xong đi đâu) · đổi câu cảnh báo/ràng buộc (AI nháp, consent, không phải kênh cấp cứu…) · đổi token màu/chữ/radius ở `design.css`.
**Không cần ghi**: refactor không đổi giao diện · test/evidence · seed/dữ liệu mẫu (trừ khi thêm cột/trạng thái mới) · sửa lỗi không đổi hiển thị.

Mẫu (mục mới lên trên cùng):

```md
### YYYY-MM-DD · <thêm|sửa|xóa> · <tên màn/tab/modal>
- Nơi sửa: `prototype/shared/<file>` · selector `data-nav="…"` / `data-tab="…"` / `data-modal="…"` / nút "…"
- Thay đổi: <trường/nút/trạng thái/câu nào thêm, bớt, đổi; luồng mới>
- Canvas dự kiến: <mã màn trong references/coverage.md, vd I2, J6 · hoặc "màn mới">
- Người ghi: <tên/agent> · commit/PR nếu có
```

Không chắc mã canvas thì ghi "chưa rõ"; skill sẽ tra trong `references/coverage.md`.

## Chờ chuyển

_(trống)_

## Đã xử lý

Skill chuyển mục từ "Chờ chuyển" xuống đây kèm kết quả, rồi cập nhật **Mốc đồng bộ** thành commit đã đối chiếu. Giữ khoảng 20 mục gần nhất; mục cũ hơn xem git history.

### 2026-09-23 · đồng bộ toàn bộ · baseline
- Dump toàn bộ Clinic Web, Patient 360, Patient Mobile, Finance; so với canvas 55 màn.
- Kết quả: thêm I1–I13, J1–J11, K1–K3 (canvas 82 màn), đẩy lên claude.ai/design. Bảng đối chiếu ở `references/coverage.md`.
