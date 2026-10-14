# Kế hoạch: plugin kỹ năng, plugin lưu hội thoại, và kho kịch bản (RAG từ hội thoại)

Trạng thái: **bản 4, user đã duyệt (2026-10-13), GĐ1 và GĐ2 đã xong (plugin `skills`, phía máy chủ và trang web: khung chat soạn skill + thêm thẳng file, không form; GĐ2 bỏ test UI, ảnh và so khớp theo user), GĐ3 đã xong (2026-10-14: đường quan sát ở lõi, Zalo chuyển tin, plugin `conversations` và trang "Hội thoại"), GĐ4 đã xong (2026-10-14: dịch vụ giữa các plugin, kho kịch bản RAG trong `conversations`, hook và tool `scenario_search`, tab "Kịch bản"), tiếp theo GĐ5.** Thay đổi so với bản 3: dữ liệu hội thoại đi vào **RAG**,
không đi vào skill; tự học skill **tạm dừng** (chiến lược để sau). User bổ sung: `conversations` thu hội thoại từ **mọi
nền tảng** gom được, không chỉ Zalo.

## 1. Mục tiêu

1. **Plugin `skills`:** kỹ năng, quy tắc (kiểu `AGENTS.md`) và persona (kiểu `SOUL.md`) trong Postgres, có lịch sử và
   khôi phục, sửa trên web, **gán theo phạm vi**: cả agent, một plugin giao diện (Zalo), hay một tài khoản (kênh).
2. **Plugin `conversations`:** cất **toàn bộ hội thoại hai vai** (khách và nhân viên), kể cả tin nghe thụ động ở nhóm lẫn
   cá nhân, từ **bất kỳ nền tảng nào gom được**; tách khỏi plugin Zalo để kênh nào cũng dùng.
3. **Kho kịch bản (RAG):** từ hội thoại đã cất, tạo các **tình huống** (khách hỏi gì, nhân viên phản ứng ra sao) để tìm
   lại khi khách hỏi câu tương tự, đưa vào ngữ cảnh của agent làm **kịch bản mẫu** cho câu trả lời chuẩn.
4. **Tạm dừng:** agent tự viết hay sửa skill. Skill chỉ do người viết trên web.

## 2. Thuật ngữ

| Từ | Nghĩa |
| --- | --- |
| Plugin | Gói cài đặt, bật/tắt được, có thể mang tool, trang, job, route, nội dung |
| Tool | Một hàm model gọi được (`skill_view`, `kb_search`) |
| Skill | Tài liệu hướng dẫn một việc, do người viết; model đọc khi cần |
| Rules, Persona | Chỉ dẫn luôn nạp (kiểu `AGENTS.md`, `SOUL.md`) |
| Phạm vi | `agent` (mọi kênh) → `plugin` (ví dụ `zalo`) → `kênh` (một tài khoản, ví dụ `zalo-<id>`) |
| Tình huống (episode) | Một câu hỏi hay yêu cầu của khách cùng phần nhân viên phản ứng, cắt từ hội thoại |
| Kịch bản | Tình huống đã được đánh chỉ mục để tìm lại (RAG) |

## 3. Hiện trạng (đã đọc code)

- Skill nằm ở lõi (`agentcore/skills`, bảng `agent_skill` không có lịch sử; mục lục nằm trong system prompt đóng băng
  theo phiên). Chưa có route hay UI. Agent ghi được skill từ lời khách (chỉ `injection_scan` chặn).
- Plugin host có: tool, prompt section, hook, kênh, job, route, trang UI, migration riêng (`[migrations] prefix`). Host
  biết kênh nào của plugin nào (`_channel_owner`, chưa mở cho plugin). Prompt section theo lượt đọc được kênh của lượt
  nhưng chạy đồng bộ, nên plugin giữ bản chụp trong bộ nhớ và làm mới bằng job (như mục lục kho tri thức).
- **Hook `pre_model` chạy bất đồng bộ và sửa được yêu cầu gửi lên model**: chỗ hợp để tìm kịch bản và đưa vào ngữ cảnh.
- Kho tri thức đã có hạ tầng RAG: dịch vụ nhúng (`embedding.py`, khóa API lưu mã hóa), bảng vector (pgvector), tìm
  lai từ khóa và vector, job nhúng nền. Hạ tầng đó nằm **bên trong plugin `knowledge`**.
- Zalo: `access.should_respond` đã quyết định `record` (nghe thụ động) nhưng lõi chưa có đường cho tin "giữ mà không
  trả lời", nên tin đó đang bị bỏ. Tin của chính tài khoản (`is_self`, tức nhân viên đang dùng Zalo cá nhân) cũng bị
  bỏ.
- Tài khoản Zalo là kênh riêng (`zalo-<account_id>`) với cấu hình riêng (allowlist, trả lời nhóm, nghe thụ động).

## 4. Plugin `skills` (GĐ1 và GĐ2; thiết kế đã được user chấp nhận ở bản 3)

- **Mục** có `kind` (`skill`, `rules`, `persona`), tên, mô tả một dòng, nội dung Markdown, trạng thái
  (`draft|active|archived`), nguồn (`admin|plugin`), `scopes`, `meta` JSONB, `usage` JSONB. Bảng phiên bản chỉ thêm,
  không sửa; khôi phục = lưu lại bản cũ thành phiên bản mới.
- **Phạm vi và thứ tự:** mỗi lượt chọn các mục khớp với kênh của lượt, xếp từ rộng đến hẹp, mục hẹp đứng sau và thắng
  khi trái nhau. Rules và persona ở phạm vi hẹp là **bổ sung**, không thay `AGENTS.md`/`SOUL.md` của agent; khối chỉ
  dẫn ghi rõ không ghi đè quy tắc của agent. Plugin khác (Zalo) gửi kèm skill và rules mặc định trong thư mục của nó,
  tự gán vào phạm vi plugin đó.
- **Nạp theo lượt**, không đóng băng: skill thêm trên web đến được phiên Zalo đang chạy ở lượt sau. Mục lục skill ≤
  `index_chars` (mặc định 6.000), rules và persona ≤ `context_chars` (mặc định 8.000); thừa thì bỏ mục chung nhất.
  Tool `skill_list`, `skill_view`, `skill_search`. Plugin giữ bản chụp trong bộ nhớ, làm mới khi đổi và mỗi 60 giây.
- **Kiểm tra mọi lần ghi:** `injection_scan`, kích thước, tên, trùng tên, phạm vi hợp lệ, cảnh báo số điện thoại/CCCD.
- **Lõi cần thêm:** mở `channel_owner` thành `ctx.channel_plugin(kênh)`. Plugin tự có migration và route; profile
  `clinic` tắt skill tự ghi của lõi (`[skills] enabled = false`) và nhập skill cũ trong `agent_skill` một lần.
- **Trang web** (`/admin/agent/skills`): danh sách, soạn (chọn phạm vi, xem trước đúng như model nhận), lịch sử và
  khôi phục, tab "Kỹ năng và quy tắc" trên trang từng tài khoản Zalo, trang "hiệu lực cho kênh này".

## 5. Plugin `conversations` (GĐ3)

**Việc:** nhận **mọi tin**, cất vào bảng riêng (prefix `cv_`), kênh nào cũng dùng.

- **Nguồn tin (cần thêm ở lõi):** (a) tin đã vào agent và câu trả lời của agent; (b) tin **nghe thụ động** mà kênh
  chuyển tiếp (nhóm không @mention, cá nhân agent không trả lời); (c) tin **nhân viên gửi** từ tài khoản Zalo cá nhân
  (`is_self`). Lõi thêm một đường "quan sát": kênh gọi `observe(tin)` cho tin giữ mà không trả lời, và plugin đăng ký
  `ctx.on_message(...)` để nhận cả tin vào lẫn tin ra. Plugin Zalo ngừng bỏ tin `record` và `is_self`, chuyển chúng qua
  đường này.
- **Vai:** mỗi tin gắn `role`: `staff` (tin của chính tài khoản, hoặc người gửi nằm trong **danh sách nhân viên** cấu
  hình theo kênh), `agent` (trả lời của AI), `customer` (còn lại).
- **Lưu:** cuộc trò chuyện (kênh, trực tiếp hay nhóm, mã cuộc trò chuyện), tin nhắn (người gửi, vai, thời điểm, văn
  bản, đã được agent trả lời hay chưa, siêu dữ liệu JSONB). Bật theo kênh hoặc cuộc trò chuyện, **mặc định tắt**.
  Thời hạn giữ cấu hình (mặc định không tự xóa), xóa theo cuộc trò chuyện.
- **Trang** "Hội thoại": danh sách, xem hai vai theo dòng thời gian, tìm, danh sách nhân viên, cài đặt giữ và xóa.
- Pháp lý (Nghị định 13/2023): user đã nói tạm bỏ qua.

## 6. Kho kịch bản: RAG trên hội thoại (GĐ4)

**Nguyên tắc (theo user):** hội thoại là **dữ liệu để tìm lại**, không biến thành skill. Chuẩn học là **cách nhân viên
phản ứng**; lời khách chỉ là bối cảnh của tình huống. Skill vẫn do người viết, không phình theo dữ liệu.

1. **Cắt tình huống (job nền):** từ hội thoại đã cất, một tình huống bắt đầu ở một tin của khách, gồm các tin kế tiếp
   đến khi khách nêu chủ đề mới hoặc im quá 30 phút. **Chỉ giữ tình huống có phản ứng của nhân viên**; tin khách đứng một
   mình không bao giờ thành kịch bản.
2. **Xử lý trước khi cất:** bỏ tình huống quá ngắn hay chỉ xã giao, **che tên, số điện thoại, CCCD, địa chỉ** (câu của
   khách A không được hiện ra cho khách B), quét `injection_scan`, gộp tình huống giống nhau và đếm số lần lặp.
3. **Đánh chỉ mục (RAG):** văn bản của tình huống gồm câu hỏi của khách và phản ứng của nhân viên, có chỉ mục từ khóa
   (Postgres) và vector (pgvector), cộng JSONB cho phần mở rộng (thẻ dịch vụ, giọng điệu, kênh nguồn).
4. **Dùng lại khi khách hỏi:** một **hook `pre_model`** lấy câu hỏi mới nhất của khách, tìm các tình huống gần nghĩa nhất
   (tìm lai như kho tri thức; ưu tiên tình huống lặp nhiều và mới), và nếu đủ giống thì thêm 2-3 tình huống vào khối ngữ
   cảnh của lượt dưới dạng **"kịch bản mẫu: cách nhân viên đã phản ứng"**, kèm lời dặn: học bước đi, giọng điệu,
   điều nên hỏi lại, lúc nào chuyển người; **số liệu (giá, chính sách) chỉ lấy từ kho tri thức** vì câu trả lời cũ có thể
   đã lỗi thời. Hook làm sẵn (model yếu cần harness làm hộ); thêm tool `scenario_search` để agent tự tìm thêm.
5. **Theo phạm vi** như plugin `skills`: kịch bản cất từ tài khoản nào dùng cho tài khoản đó hay cho cả plugin, cấu hình
   được. Công tắc bật/tắt theo phạm vi, nút xóa từng tình huống.
6. **Không duyệt** (tạm thời, theo user): tự động từ lúc có dữ liệu.
7. **Trang** "Kịch bản": tình huống đã cất, số lần lặp, thử tìm một câu hỏi, xóa, công tắc theo phạm vi.

**Dùng chung dịch vụ nhúng:** hạ tầng nhúng hiện nằm trong plugin `knowledge`. Đề xuất: thêm một **cơ chế dịch vụ giữa các
plugin** nhỏ ở lõi (`ctx.provide("embeddings", ...)` và `ctx.use("embeddings")`): `knowledge` cung cấp, `conversations` dùng.
Không bật `knowledge` hay chưa nối dịch vụ nhúng thì kho kịch bản tìm bằng từ khóa (như kho tri thức đã làm).

## 7. Các giai đoạn

| GĐ | Nội dung | Kết quả kiểm tra |
| --- | --- | --- |
| 1 | Plugin `skills` phần sau máy chủ: migration, store (Postgres và bộ nhớ), phạm vi, prompt section theo lượt, tool, kiểm tra, route admin, nhập skill cũ; `ctx.channel_plugin`; profile `clinic` tắt skill tự ghi | Test phạm vi (agent/plugin/kênh), route, lịch sử; Postgres trên `agent_activity_test`; skill gán `zalo-A` không hiện ở `zalo-B` |
| 2 | Trang web skills (danh sách, soạn, lịch sử, tab theo tài khoản, "hiệu lực cho kênh này") | Test UI, ảnh so sánh canvas; thêm skill trên web thì phiên đang chạy thấy ở lượt sau |
| 3 | Lõi: đường "quan sát" và `ctx.on_message`; Zalo chuyển tin thụ động và `is_self`; plugin `conversations` (lưu, vai, danh sách nhân viên, trang) | Tin nhóm không @mention và tin nhân viên được lưu mà không có lượt agent; agent không trả lời tin thụ động |
| 4 | Cơ chế dịch vụ giữa plugin; cắt tình huống, che thông tin, chỉ mục từ khóa và vector; hook `pre_model` và tool `scenario_search`; trang "Kịch bản" | Test với dữ liệu giả; câu hỏi lặp thì lấy đúng tình huống; kịch bản không bao giờ thay số liệu của kho |
| 5 | Bộ câu hỏi đánh giá agent trước/sau khi có kịch bản; số đo | Số đo trước/sau |
| (tạm dừng) | Agent tự viết hay sửa skill; hàng chờ duyệt; dọn skill cũ | Chiến lược để sau |

Dữ liệu thử là **dữ liệu giả** (quy tắc dự án); trước khi có dữ liệu thật, bộ hội thoại giả hai vai được sinh để thử.

## 8. Rủi ro

- **Kịch bản chứa thông tin cá nhân hay số liệu cũ:** che thông tin trước khi cất; số liệu chỉ từ kho tri thức; kịch bản
  ghi ngày; có thể xóa và tắt theo phạm vi.
- **Đầu độc qua lời khách:** chỉ tình huống có phản ứng của nhân viên mới được cất; kịch bản là dữ liệu đặt trong khung
  "ví dụ, không phải chỉ dẫn"; quét `injection_scan` khi đánh chỉ mục; không thành skill hay quy tắc.
- **Nhân viên phản ứng chưa chuẩn bị bị học theo:** user đã chọn không duyệt; có công tắc theo phạm vi, xóa từng tình
  huống, và bộ đánh giá GĐ5 để thấy kịch bản làm câu trả lời tốt hay xấu đi.
- **Nhầm vai (khách bị coi là nhân viên):** vai suy từ tài khoản và danh sách nhân viên cấu hình, không từ nội dung tin
  nhắn.
- **Kịch bản trái quy tắc an toàn:** quy tắc của agent đứng trên; khối kịch bản ghi rõ.
- **Skill hẹp làm yếu quy tắc an toàn:** rules, persona ở phạm vi hẹp chỉ bổ sung, không thay thế.
- **Độ trễ của hook:** tìm kịch bản thêm một lần nhúng câu hỏi trước khi gọi model (kho tri thức đo được ~2 s, tối đa
  ~7,6 s); nhúng dùng chung bộ nhớ đệm câu hỏi; hết thời hạn thì bỏ qua kịch bản, agent trả lời như thường.
- **Lưu toàn bộ hội thoại** là dữ liệu cá nhân: pháp lý tạm bỏ qua theo user; vẫn giữ công tắc theo kênh, quyền đọc, xóa.

## 9. Đã duyệt (2026-10-13)

1. Hai plugin (`skills`, `conversations`), kho kịch bản nằm trong `conversations`; `conversations` thu từ mọi nền tảng.
2. Dịch vụ nhúng dùng chung qua cơ chế dịch vụ giữa plugin (`ctx.provide`/`ctx.use`).
3. Hook tự thêm kịch bản vào ngữ cảnh khi đủ giống, cộng tool `scenario_search`.
4. Không đổi (lấy mặc định): tin của chính tài khoản là nhân viên, người khác theo danh sách nhân viên cấu hình; tình huống
   bắt đầu ở tin khách và kết thúc khi khách nêu chủ đề mới hoặc im 30 phút, chỉ giữ tình huống có nhân viên phản ứng;
   hội thoại mặc định không tự xóa.

## 10. Ngoài phạm vi (đã hoãn)

Hook cờ đỏ trước khi gọi model, chặn ghi memory theo kênh bằng hook, hai skill quy trình (`tiep-nhan-dat-lich`,
`xu-ly-phan-nan`; sẽ viết bằng chính trang skills khi xong GĐ2), tự học skill kiểu Hermes (bộ đếm, review nền, hàng chờ
duyệt, dọn skill cũ): chiến lược để sau.
