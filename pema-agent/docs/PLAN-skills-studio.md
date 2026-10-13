# Kế hoạch: plugin kỹ năng (skill, quy tắc, persona), trang quản lý, tự học, và plugin lưu hội thoại

Trạng thái: **bản 3, user đã xác nhận mục 9 (2026-10-13), đang làm GĐ1.** Bản 1 và 2 đã được user trả lời; bản này
ghi lại các câu trả lời, trong đó việc **tự học đổi thành kho dữ liệu kịch bản, không duyệt**.

## 1. Mục tiêu

1. Kỹ năng, quy tắc (`AGENTS.md`) và persona (`SOUL.md`) là nội dung của **một plugin**, nằm trong Postgres, có
   lịch sử và khôi phục, sửa được trên web.
2. **Gán theo phạm vi:** cả agent, một plugin giao diện (ví dụ Zalo), hay một tài khoản cụ thể (ví dụ tài khoản Zalo
   của lễ tân), như cách plugin được bật và cấu hình.
3. Agent học **kịch bản** từ cách nhân viên trả lời khách (nghe thụ động), lưu thành **dữ liệu** (vector và JSON) để
   lấy ra khi khách hỏi câu tương tự. **Không duyệt** (tạm thời) và **không học chỉ dẫn từ lời khách**.
4. Sau đó: plugin **lưu toàn bộ hội thoại** (cả tin không được trả lời, nghe thụ động ở nhóm lẫn cá nhân), tách
   khỏi plugin Zalo để mọi kênh dùng chung.

## 2. Thuật ngữ

| Từ | Nghĩa |
| --- | --- |
| Plugin | Gói cài đặt, bật/tắt được, có thể mang tool, trang, job, route, nội dung |
| Tool | Một hàm model gọi được (`skill_view`, `kb_search`) |
| Skill | Tài liệu hướng dẫn cho một việc, model đọc khi cần |
| Rules, Persona | Chỉ dẫn luôn nạp (kiểu `AGENTS.md`, `SOUL.md`) |
| Gán (binding) | Một mục (skill, rules, persona) áp cho một phạm vi |
| Phạm vi | `agent` (mọi kênh) → `plugin` (ví dụ `zalo`) → `kênh` (một tài khoản, ví dụ `zalo-<id>`) |

## 3. Hiện trạng (đã đọc code)

- Skill nằm ở lõi: `agentcore/skills`, bảng `agent_rt.agent_skill` (có `version`, không có lịch sử), tool
  `skill_list/view/write/patch`. Mục lục skill nằm trong system prompt **đóng băng theo phiên**. Chưa có route hay UI.
- Agent ghi được skill từ lời của khách trên Zalo (chỉ có `injection_scan` chặn).
- Plugin đang có: `contributions` gồm tool, prompt section, hook, kênh, job, authenticator, route, trang UI, migration
  riêng (`[migrations] prefix`). Host biết kênh nào của plugin nào (`channel_owner`), nên phạm vi "plugin" và "kênh"
  suy ra được từ tên kênh của lượt (`TurnInfo.channel`, ví dụ `zalo-<id>`).
- **Prompt section theo lượt** đọc được `TurnInfo.channel` nhưng chỉ chạy đồng bộ: plugin phải giữ bản chụp trong bộ
  nhớ và làm mới bằng job (như mục lục kho tri thức, `plugin.py` của `knowledge`).
- Zalo: `access.should_respond` đã quyết định `record` (nghe thụ động ở nhóm không @mention) nhưng **lõi chưa có
  đường cho tin "giữ mà không trả lời", nên plugin hiện bỏ tin đó** (ghi chú trong `access.py`).
- Tài khoản Zalo là kênh riêng (`zalo-<account_id>`), mỗi cái có cấu hình riêng (allowlist, trả lời nhóm, nghe thụ
  động).

## 4. Hermes (đã đọc `hermes-agent`) và lấy gì

| Hermes | Pema |
| --- | --- |
| Bộ đếm (10 lượt/10 vòng tool) rồi chạy review ở nền sau khi đã trả lời; counter về 0 khi model tự ghi | Có |
| Review = một lần chạy agent riêng, tối đa 16 bước, chỉ có tool skill, đọc trước khi ghi | Có (tối đa 12 bước) |
| Ưu tiên: sửa skill đã nạp > sửa skill chung > thêm file tham chiếu > tạo mới; lời chỉnh giọng điệu là tín hiệu hạng nhất; không tạo theo vụ việc đơn lẻ; không xóa | Có |
| Sổ cái thay đổi, khôi phục từng mục | Có (bảng phiên bản) |
| Hàng chờ duyệt, quét bảo mật skill do agent viết: **tắt mặc định** | **Bật mặc định** |
| Giọng điệu vào skill của việc đó, hoặc vào bộ nhớ người dùng nếu áp mọi việc, "không bao giờ cả hai" | Có |
| Curator: 14 ngày không dùng thì "cũ", 30 ngày thì lưu trữ, không xóa cứng | GĐ sau |
| Đánh giá chất lượng skill tự viết | Hermes không có; Pema dùng người duyệt và bộ câu hỏi đánh giá |

## 5. Thiết kế (theo câu trả lời của user)

**K1. Plugin `skills` (câu trả lời 1 và 4).** Một plugin mang: bảng riêng (prefix `sk_`, migration của plugin), tool
`skill_list`, `skill_view`, `skill_search`, route admin, trang UI, job làm mới bản chụp.
Profile đặt `[skills] enabled = false` ở lõi và bật plugin này; skill tự viết cũ trong `agent_skill` được nhập một lần.
Skill gói sẵn của profile (thư mục `skills/`) vẫn chỉ đọc.

**K2. Ba loại mục, một cách gán.** Mỗi mục có `kind` (`skill`, `rules`, `persona`), nội dung, trạng thái
(`draft|active|archived`), nguồn (`admin|plugin|agent`), `scopes` (danh sách phạm vi; rỗng = cả agent), `meta`
JSONB (thẻ, ví dụ câu mẫu), `usage` JSONB (đếm xem/dùng/sửa). Bảng phiên bản chỉ thêm, không sửa.

**K3. Phạm vi và thứ tự (câu trả lời 1).** Lúc mỗi lượt, bản chụp cho kênh của lượt chọn các mục có phạm vi khớp:
`agent` luôn khớp, `plugin:zalo` khớp mọi kênh của Zalo, `channel:zalo-<id>` chỉ khớp tài khoản đó. Xếp **từ rộng đến
hẹp, mục hẹp đứng sau và thắng khi trái nhau**. `rules` và `persona` ở phạm vi hẹp là phần **bổ sung** cho
`AGENTS.md`/`SOUL.md` của agent, không thay thế: quy tắc an toàn của agent đứng trên, và khối chỉ dẫn nói rõ điều đó
("không ghi đè quy tắc của agent"). Plugin khác (Zalo) có thể gửi kèm skill và rules mặc định trong thư mục của nó,
tự gán vào phạm vi plugin đó; mục trong DB do admin tạo thì ghi đè theo tên.

**K4. Nạp theo lượt, nhiều tùy ý (câu trả lời 2).** Mục lục skill và nội dung `rules`/`persona` đi trong khối ngữ cảnh
của từng lượt (không đóng băng, không phá prompt cache), như mục lục kho tri thức. Số lượng không giới hạn cứng trong
DB; ngân sách mục lục là cấu hình (mặc định 6.000 ký tự), thừa thì mục lục cắt và dặn dùng `skill_search`. Skill thêm
trên web đến được phiên Zalo đang chạy ở lượt kế tiếp (bản chụp làm mới khi đổi và mỗi 60 giây).

**K5. Kho kịch bản: dữ liệu, không phải chỉ dẫn (câu trả lời 3).** Khác với skill, kịch bản **không** thành chỉ dẫn của
agent. Đó là dữ liệu: "khi khách hỏi như thế này, nhân viên đã trả lời như thế này".
1. **Nguồn duy nhất là cách nhân viên trả lời.** Plugin lưu hội thoại (K7) ghi cả tin nhân viên gửi từ tài khoản Zalo cá
   nhân (tin của chính tài khoản, `is_self`). Job ghép "tin khách + tin nhân viên trả lời" thành một cặp. Tin khách
   đứng một mình không bao giờ tạo mục: **không học linh tinh từ khách**.
2. **Xử lý trước khi cất:** bỏ cặp quá ngắn hay chỉ xã giao ("dạ", "ok"), che tên, số điện thoại, CCCD, địa chỉ
   (một câu trả lời nhắc tên khách A không được hiện ra cho khách B), quét `injection_scan`, đo vector của câu hỏi
   (cùng dịch vụ nhúng của kho tri thức), gộp các câu hỏi giống nhau và đếm số lần lặp.
3. **Cất:** bảng riêng (câu hỏi, các bản trả lời của nhân viên, thẻ giọng điệu, số lần lặp, nguồn, ngày), kèm vector;
   JSONB cho phần mở rộng. **Không duyệt**: tự động, tạm thời theo ý user; có công tắc bật/tắt theo phạm vi và nút xóa.
4. **Dùng:** khi khách hỏi, tìm các câu hỏi đã cất gần nghĩa nhất (ưu tiên câu lặp nhiều) và đưa 2-3 cặp vào khối ngữ
   cảnh của lượt như **ví dụ cách nhân viên đã trả lời**, kèm lời dặn: dùng để học giọng điệu và các bước; **số liệu
   (giá, chính sách) chỉ lấy từ kho tri thức**, vì câu trả lời cũ có thể đã lỗi thời. Hook trước khi gọi model làm việc
   này (model yếu cần harness làm sẵn), cộng một tool `scenario_search` để agent tìm thêm.
5. **Theo phạm vi** như K3: kịch bản học từ tài khoản nào dùng cho tài khoản đó hoặc cho cả plugin, cấu hình được.
Phần chỉ dẫn (skill, rules, persona) vẫn do người viết trên web; nếu sau này muốn agent đề xuất sửa chỉ dẫn thì dùng
hàng chờ duyệt (đang hoãn).

**K6. Kiểm tra mọi lần ghi.** Tái dùng `injection_scan` và mẫu đe dọa của lõi trên mọi nội dung (kể cả admin dán vào),
kích thước, tên, trùng tên, mẫu số điện thoại/CCCD, câu dặn bỏ qua quy tắc, gọi tool bị cấm. Số liệu (giá, chính sách)
không vào skill mà ở kho tri thức.

**K7. Plugin lưu hội thoại `conversations` (câu trả lời 6; là nguồn của K5 nên làm trước K5).** Plugin riêng, không phụ thuộc kênh: nhận
**mọi tin** qua hai nguồn: tin đã đưa vào agent, và tin **nghe thụ động** (nhóm không @mention, cá nhân chưa trả lời)
mà kênh chuyển tiếp. Lưu vào bảng riêng (kênh, cuộc trò chuyện, người gửi, thời điểm, văn bản, loại, đã trả lời hay
không, siêu dữ liệu). Cần ở lõi: một đường **"quan sát"** cho kênh (kênh gọi `observe(InboundMessage)` cho tin giữ mà
không trả lời; một hook cho plugin nhận tin vào và tin trả ra). Plugin Zalo bỏ việc tự bỏ tin `record`, và chỉ
chuyển nó qua đường quan sát. Cấu hình: bật theo kênh, theo cuộc trò chuyện (nhóm/cá nhân), thời hạn giữ, che thông tin
cá nhân khi lưu hay khi đọc, quyền đọc, nhật ký truy cập, xóa theo yêu cầu. Mặc định tắt.

## 6. Màn hình (Next.js, `/admin/agent/...`, theo plugin)

1. **Kỹ năng:** danh sách (tên, loại, trạng thái, nguồn, phạm vi, số lần dùng); lọc theo phạm vi/kênh; "Thêm".
2. **Soạn:** tên, mô tả, **phạm vi (chọn: cả agent / plugin / tài khoản)**, thân Markdown với bản xem trước đúng như
   model nhận, trạng thái, cảnh báo kiểm tra.
3. **Lịch sử:** phiên bản, so sánh, khôi phục.
4. ~~Hàng chờ duyệt~~ **hoãn** (không có đề xuất cần duyệt khi chưa cho agent sửa chỉ dẫn).
5. **Theo tài khoản:** trên trang tài khoản Zalo, tab "Kỹ năng và quy tắc" xem và gán mục cho tài khoản đó (cùng dữ
   liệu với trang 1).
6. **Hội thoại (GĐ3):** cuộc trò chuyện đã lưu, tìm, xem, cài đặt giữ/xóa.
7. **Kịch bản (GĐ4):** các cặp đã cất, số lần lặp, tìm thử, xóa, công tắc theo phạm vi.

UI theo quy tắc dự án: mã màn hình trong `design-specs/web/INDEX.md`, spec và ảnh canvas, subagent `pema-ui-builder`,
chụp so sánh, ghi `web-design-changes.md`. Chưa có màn hình tương ứng thì nói rõ trong báo cáo.

## 7. Các giai đoạn

| GĐ | Nội dung | Kết quả kiểm tra |
| --- | --- | --- |
| 1 | Plugin `skills`: migration, store (Postgres và bộ nhớ), phạm vi, bản chụp và prompt section theo lượt, tool, kiểm tra K6, route admin, nhập skill cũ; profile `clinic` tắt skill tự ghi của lõi | Test thư viện, route, phạm vi (agent/plugin/kênh), Postgres trên `agent_activity_test`; skill gán `zalo-A` không hiện ở `zalo-B` |
| 2 | Trang web: danh sách, soạn, lịch sử, tab theo tài khoản, "hiệu lực cho kênh này" | Test UI, ảnh so sánh canvas; thêm skill trên web thì phiên đang chạy thấy ở lượt sau |
| 3 | Plugin `conversations` và đường quan sát ở lõi; Zalo chuyển tin thụ động và tin của nhân viên; trang hội thoại | Test; tin nhóm không @mention và tin `is_self` được lưu mà không có lượt agent |
| 4 | Kho kịch bản (K5): job ghép cặp, che thông tin, vector, tìm; hook đưa ví dụ vào lượt; tool `scenario_search`; trang Kịch bản | Test với model và dịch vụ nhúng giả; đo trên bộ câu hỏi lặp: câu có kịch bản thì được lấy ra; không bao giờ có số liệu từ kịch bản thay cho kho |
| 5 | Đếm sử dụng, đánh dấu cũ, lưu trữ (curator); bộ câu hỏi đánh giá agent trước/sau | Số đo trước/sau |

## 8. Rủi ro

- **Đầu độc qua lời khách:** chỉ cặp có câu trả lời của nhân viên mới được cất; kịch bản là dữ liệu đặt trong khung
  "ví dụ, không phải chỉ dẫn", quét `injection_scan` khi cất; không thành skill.
- **Kịch bản lỗi thời hoặc sai số liệu:** số liệu chỉ lấy từ kho tri thức; ví dụ ghi ngày; có thể xóa và tắt theo phạm vi.
- **Skill trái nhau giữa các phạm vi:** thứ tự rộng→hẹp rõ ràng; người duyệt thấy bản so sánh; trang "hiệu lực cho kênh
  này" hiện danh sách mục sẽ được nạp theo đúng thứ tự.
- **Skill hẹp làm yếu quy tắc an toàn:** quy tắc của agent đứng trên và chỉ bổ sung ở mức hẹp; không có "thay thế".
- **Chi phí model của job học:** ngân sách token, model rẻ chọn trong cấu hình, mặc định tắt cho kênh khách.
- **Lưu toàn bộ hội thoại (K7)** là dữ liệu cá nhân: user đã nói tạm bỏ qua phần pháp lý (Nghị định 13/2023). Vẫn giữ
  các điều khiển kỹ thuật (bật theo kênh, thời hạn giữ, quyền đọc, xóa) và che thông tin cá nhân trước khi dùng làm kịch bản.
- **Plugin phụ thuộc lẫn nhau:** `skills` đọc nguồn học từ `conversations` qua một cổng hẹp, không import trực tiếp.

## 9. Đã xác nhận (2026-10-13)

1. "Positive" = passive, nghe thụ động mà không trả lời.
2. Rules và persona ở phạm vi hẹp là bổ sung, không thay thế.
3. Học từ cách **nhân viên** trả lời qua nghe thụ động; **tạm không duyệt**; cất vào vector và JSON làm dữ liệu cho
   ngữ cảnh của AI; không học chỉ dẫn từ lời khách; khi khách hỏi câu đã gặp thì lấy kịch bản ra dùng.
4. Lưu hội thoại mặc định tắt, bật theo kênh hoặc cuộc trò chuyện.
5. Làm theo thứ tự GĐ1, GĐ2, rồi GĐ3, GĐ4, GĐ5.
6. Pháp lý (Nghị định 13/2023): tạm bỏ qua.

## 10. Ngoài phạm vi (đã hoãn)

Hook cờ đỏ trước khi gọi model, chặn ghi memory theo kênh bằng hook (phần skill được K1 giải quyết), hai skill quy trình
`tiep-nhan-dat-lich` và `xu-ly-phan-nan` (sẽ viết bằng chính trang quản lý này khi xong GĐ2).
