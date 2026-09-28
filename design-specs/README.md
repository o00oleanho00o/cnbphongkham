# design-specs — spec/prompt từng màn Pema

Mỗi màn của design canvas `Pema App redesign canvas/Pema App.dc.html` (A1 … K3) có một spec đủ để dựng lại hoặc chuyển đổi màn đó **mà không phải đọc lại web, Flutter hay canvas** — giống cách Stitch / Claude Design giữ prompt phía sau mỗi màn.

| File | Nội dung | Ai sửa |
|---|---|---|
| `screens/<ID>.md` | Spec + prompt của một màn | Sinh tự động |
| `INDEX.md` | Danh mục 82 màn: nguồn logic, composable KMP, module, đã port | Sinh tự động |
| `BLOCKS.md` | Bảng tra helper block canvas → component Compose | Sinh tự động |
| `index.json` | Toàn bộ dữ liệu trên dạng JSON | Sinh tự động |
| `notes.json` | Ghi chú chuyển đổi: nguồn web, quy tắc nghiệp vụ, khác biệt được chấp nhận, bẫy đã gặp, việc còn lại | **Người / agent** |

Mỗi spec gồm:
- **Nguồn logic**: màn Flutter (class + file, suy ra từ `app_router.dart`) hoặc trang/tab/modal web.
- **KMP**: route (`Routes.X`), composable + file, graph, hàm domain `shared/clinic`, shot test và ảnh so sánh.
- **Khung + Bố cục**: từng block canvas dịch sẵn sang Compose (`PemaHeading(…)`, `PemaInfoCard { … }`…), đúng thứ tự từ trên xuống, kèm chữ thật.
- **Câu bắt buộc** (notice trên canvas), **Quy tắc nghiệp vụ**, **Khác biệt được chấp nhận**, **Bẫy đã gặp** (từ `notes.json`).
- **Prompt** sẵn dùng.

Phần tự sinh đọc thẳng từ canvas và code nên không bao giờ lệch; phần hiểu biết (vì sao, quy tắc, bẫy) nằm trong `notes.json`.

## Cập nhật
```powershell
node .claude\skills\pema-canvas-to-kmp-compose\scripts\design-specs.cjs            # sinh lại
node .claude\skills\pema-canvas-to-kmp-compose\scripts\design-specs.cjs --check    # báo lỗi nếu lỗi thời
node .claude\skills\pema-canvas-to-kmp-compose\scripts\design-specs.cjs --show=I2  # in một spec
```
Trong `pema-kmp`, task Gradle `designSpecs` chạy sau mỗi `jvmTest` (bỏ qua nếu canvas, code và notes không đổi).

**Sau khi chuyển đổi hoặc sửa một màn**, ghi lại điều đã học (nguồn hàm web, câu lỗi, quyết định, bẫy) để lần sau khỏi tìm lại: thêm vào `notes.json` (khóa `screens.<ID>.logic | rules | differences | gotchas | todo`) rồi chạy lệnh sinh lại, hoặc gọi tool MCP `record_note`. Không sửa trực tiếp `screens/*.md`.

## MCP server `pema-design`
Server stdio, không cần cài gì thêm ngoài Node: `.claude/skills/pema-canvas-to-kmp-compose/mcp/pema-design-mcp.cjs`. Dữ liệu dựng trực tiếp từ canvas + code + notes mỗi lần gọi.

| Loại | Tên | Dùng để |
|---|---|---|
| tool | `list_screens(group?, query?)` | Danh sách màn, lọc theo nhóm A–K / từ khóa |
| tool | `get_screen(id, format?)` | Spec đầy đủ (markdown hoặc json) |
| tool | `get_screen_image(id, kind?)` | Ảnh canvas (`design-ref`) hoặc ảnh so sánh `-vs.png` |
| tool | `get_block_catalog()` | Bảng block canvas → Compose |
| tool | `record_note(id, kind, text)` | Lưu điều học được vào `notes.json` và cập nhật spec |
| tool | `regenerate_specs()` | Sinh lại cả thư mục |
| prompt | `port_screen(id)` và `A1` … `K3` | Prompt dựng/chuyển màn kèm spec |
| resource | `pema-design://screens/<ID>`, `pema-design://index`, `pema-design://blocks` | Đọc spec như tài liệu |

**Đăng ký:**
- **Claude Code**: đã có `.mcp.json` ở gốc repo (xác nhận khi mở dự án).
- **VS Code (Copilot / agent mode)**: đã có `.vscode/mcp.json`.
- **GitHub Copilot CLI**: gõ `/mcp add`, tên `pema-design`, loại `stdio`/local, lệnh `node`, tham số `E:\Desktop\cnbphongkham\.claude\skills\pema-canvas-to-kmp-compose\mcp\pema-design-mcp.cjs`.
- **Android Studio / IntelliJ (GitHub Copilot)**: Settings › Tools › GitHub Copilot › MCP › *Edit mcp.json*, thêm vào `servers`:
  ```json
  "pema-design": { "type": "stdio", "command": "node", "args": ["E:/Desktop/cnbphongkham/.claude/skills/pema-canvas-to-kmp-compose/mcp/pema-design-mcp.cjs"] }
  ```
- Thử nhanh: `npx -y @modelcontextprotocol/inspector --cli node .claude/skills/pema-canvas-to-kmp-compose/mcp/pema-design-mcp.cjs --method tools/call --tool-name get_screen --tool-arg id=I2`

Không có MCP thì đọc thẳng `screens/<ID>.md` — cùng nội dung.
