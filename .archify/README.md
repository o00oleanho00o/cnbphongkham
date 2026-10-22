# Đọc bộ sơ đồ này như thế nào

Thư mục này là bản đồ của project Pema Digital Clinic, vẽ từ mã nguồn (commit `7d86533`, 2026-10-22). Mỗi sơ đồ là một file HTML tự chứa, mở bằng trình duyệt, không cần cài gì.

## Bắt đầu từ đâu

Mở `index.html`. Đó là trang dẫn đường duy nhất; mọi sơ đồ khác đều đi từ đó. Đọc từ trên xuống:

1. **Tổng quan cả project**: ba thế hệ giao diện, tài liệu, và hệ thống mới `pema-agent`.
2. **Lõi agent** (mục 2, phần quan trọng nhất): agent là gì và vận hành ra sao.
3. **Stack đang chạy**: các container, hai database, đường ra internet.
4. **Từng luồng của plugin CRM**: đặt lịch, nhắc lịch, dữ liệu CRM vào agent.

Nếu chỉ có 15 phút, đọc ba sơ đồ: *Tổng quan cả project* → *Giải phẫu agent* → *Một lượt của agent*.

## Thứ tự đọc mục 2 (lõi agent)

Mục 2 chia bốn nhóm, mỗi nhóm trả lời một câu hỏi. Đọc theo thứ tự a → d.

**2a. Nó gồm những gì?**

| Sơ đồ | Trả lời câu hỏi |
|---|---|
| Giải phẫu agent | Lõi `agentcore` có gì, lớp `agent_app` lắp ráp thế nào, bốn UI (Zalo, HTTP, agent chat, trang quản trị) chỉ là cửa vào |
| Khởi động agent serve | Khi chạy `agent serve`, cái gì được dựng, bốn vòng nền nào chạy, tắt ra sao |
| Bản đồ mã | File nào làm gì, hướng phụ thuộc, nên mở file nào trước |

**2b. Một tin nhắn được xử lý ra sao?**

| Sơ đồ | Trả lời câu hỏi |
|---|---|
| Một lượt của agent | Từ tin đến trả lời đi qua những bước nào (dạng trình tự) |
| Vòng lặp run_turn | Mỗi bước model ↔ tool, giới hạn (bước, giờ, token, lặp), đường khôi phục (thử lại, nén, lời gọi cuối) |
| Model thấy gì mỗi lần gọi | Bốn lớp của một yêu cầu gửi model, và thứ model không bao giờ thấy |
| Nén ngữ cảnh và ghi chú | Phiên dài thì cắt ở đâu, tóm tắt lưu đâu, ghi chú sống qua phiên thế nào |
| Vòng đời một tin đến | Trạng thái của tin trong hàng đợi và của việc gửi trả lời; chuyện gì xảy ra khi tiến trình chết |

**2c. Plugin cắm vào đâu?** (hệ thống là plugin-first: lõi chỉ có 4 tool, mọi thứ khác là plugin)

| Sơ đồ | Trả lời câu hỏi |
|---|---|
| Plugin góp gì vào agent | Hợp đồng `register(ctx)`: 10 kiểu đóng góp, plugin nào dùng kiểu nào, danh sách tool đã duyệt |
| Bật plugin lúc đang chạy | Admin bật một plugin thì chuyện gì xảy ra, ở mọi tiến trình |
| Cổng và lớp cắm của lõi | Muốn thay model, kho lưu, kênh chat thì viết lớp nào |
| Kho tri thức và vector | Tài liệu vào thế nào, tìm bằng từ khóa và vector ra sao |

**2d. Vòng chủ động và dữ liệu**

| Sơ đồ | Trả lời câu hỏi |
|---|---|
| Vòng chăm sóc lại | Khách im thì agent tự nhắn lại theo luật nào; model chỉ góp ý, mã quyết |
| Schema agent_rt | 14 bảng của lõi, mọi cột, bảng nào nối bảng nào |

## Cách dùng một sơ đồ

- **Bấm vào một khối** để xem nó trích file và dòng mã nào. Đó là bằng chứng: mỗi khối đều chỉ về mã thật, không vẽ theo trí nhớ.
- **Thẻ dưới sơ đồ** ("cards") chứa những điều không vẽ được thành khối: điều kiện, con số, giới hạn, và những gì sơ đồ cố ý bỏ.
- **Nút Live / Still** bật tắt chuyển động của các đường.
- Chữ trên khối bằng tiếng Việt; khung điều khiển của trình xem bằng tiếng Anh.
- Hai sơ đồ *Vòng lặp run_turn* và *Schema agent_rt* vẽ ở mức dày hơn (standard) vì nhiều chi tiết; phóng to khi đọc.

## Khi sơ đồ và mã khác nhau

Mã là sự thật, sơ đồ là ảnh chụp tại commit `7d86533`. Nếu thấy lệch:

1. Mở `candidate.json` trong thư mục của sơ đồ đó, sửa khối hay mũi tên.
2. Chạy lại từ thư mục gốc repo:

```bash
node "<đường dẫn archify>/bin/archify.mjs" finalize <loại> .archify/<thư mục>/candidate.json .archify/<thư mục>/<tên>.html --repo-root . --quality showcase --json
```

`<loại>` là tiền tố của tên thư mục (`architecture`, `sequence`, `workflow`, `dataflow`, `lifecycle`, `erd`, `class`, `tree`). Lệnh kiểm tra cả mốc dòng mã, nên một dòng mã đã đổi sẽ bị báo.

3. Chỉ commit `*.html`, `candidate.json` và `index.html`. Các file `*.finalize*.json`, `*.browser-check.json`, `*.delivery.json` và thư mục `review-*` là biên lai kiểm tra, chứa đường dẫn máy cục bộ, không commit.

## Những gì chưa vẽ

Bên trong plugin Zalo (cầu nối, tài khoản), `sso`, `web`, `conversations`, Studio soạn kỹ năng, và các phần ngoài agent (app Android, thiết kế, web cũ). Các luật ranh giới agent ↔ CRM nằm ở `.claude/rules/agent-crm-boundary.md`; sơ đồ *Dữ liệu CRM vào agent* (mục 4) vẽ luật L4 trong số đó.
