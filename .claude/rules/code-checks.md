# Kiểm tra code: chỉ cần không làm code chết

Áp cho mọi lần viết hoặc sửa code trong repo này, kể cả do subagent làm. Chủ hệ thống chốt (2026-10-23).

- **Tiêu chuẩn duy nhất:** code chạy được. Frontend: `bun run build` không lỗi. Backend: import và khởi động được, không
  lỗi cú pháp hay lỗi chạy. Cái gì không làm code chết thì bỏ qua.
- **Không cần chạy, không cần sửa:** `ruff`, `pyright`, `bun run typecheck`, `bun run lint`, `prettier`, `import-linter`,
  cảnh báo của trình biên dịch. Không báo cáo chúng, không mất công làm sạch warning, không đổi code chỉ để đẹp hơn.
  Lỗi của chúng không chặn việc báo xong.
- **Quy tắc phong cách bỏ qua** (cả các file trong `~/.claude/rules/` như `coding-guidelines`, `type-safety`, `quality`,
  `performance` khi làm trong repo này): cấm `any`, cấm `as`/`!`, cấm `switch`/`for`/`let`, không `console.log`, TODO phải có
  số issue, import không dùng, câu `if` lồng nhau, re-render thừa… Viết theo kiểu code xung quanh, miễn chạy được.
- **Vẫn giữ** vì chúng làm hại thật, không phải vì đẹp: không để lộ khóa hay mật khẩu trong file (`security.md`), không
  ghi tên AI vào git, các luật L1–L7 và H1–H11 về ranh giới agent ↔ CRM và harness.
- Cấu hình `ruff`/`pyright`/`eslint` và target `make lint`/`make typecheck` vẫn nằm trong repo cho ai muốn chạy; không bắt buộc.
