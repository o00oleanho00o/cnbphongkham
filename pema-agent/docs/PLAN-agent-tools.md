# Kế hoạch: tool web chung cho agent (web_search, web_fetch) và vòng chăm sóc lại

**Trạng thái (2026-10-16): kế hoạch bản 5 (thêm mục 2b: cài đặt agent lên UI). Bước 0, 0a, 0b và 1 đã làm (bước 1 đúng như kế hoạch; phần đề xuất thêm ở mục 2c chờ chủ xem xét); bước 2 (`web_search`, `web_fetch`) đã làm, tool mặc định TẮT; bước 3 (vòng chăm sóc lại, nửa XÉT) đã làm, mặc định TẮT; chờ bước 4 (nửa LÀM). Bước 0 (bỏ `allow_internet`, `ToolSpec.network`) đã làm; các bước sau chờ chủ.**

Nguồn để port (chỉ đọc): `zalo-agent/src/agent/tools/web-*.ts`, `wrap-untrusted-content.ts`, `shared/safe-remote-download.ts`.
Bản ghi quy tắc tool: `project-agent-tool-rule` (2026-10-12; sẽ sửa ở bước cuối).

## 1. Chủ đã quyết

| Việc | Quyết định |
|---|---|
| Cờ `allow_internet` | **Bỏ hẳn** (đã làm, `64e85e15`). Thay bằng **tool thường**: `web_search`, `web_fetch` được bật cho agent thì agent ra được internet, không thì không (2026-10-16) |
| Cấu hình nằm ở đâu | `agent.toml` nằm trong ảnh Docker, đổi phải dựng lại. **Mọi thứ người vận hành đổi lên DB + UI** (mục 2b); TOML chỉ giữ giới hạn kỹ thuật và an toàn, và làm mặc định lúc mới cài |
| `send_file`, kho tệp, `create_word_document`, `create_excel_file`, `read_image`, `create_image`, `tai_video` | Bỏ |
| `schedule_task` (lịch cố định do model đặt) | **Bỏ**, thay bằng **vòng chăm sóc lại** (mục 5): AI tự phán đoán khi nào nhắn lại, khi nào ngưng |
| Gói thêm | Không gói mới; `httpx` khai rõ trong lõi |
| Chỗ đặt | Tool web là **tool thường của lõi**, cạnh `get_datetime`; **không phải plugin**. Vòng chăm sóc lại là phần chung của app |
| Giao diện danh sách chăm sóc lại / ngưng | Tạm bỏ, làm sau |
| Khung mặc định của vòng chăm sóc lại | Đồng ý như đề xuất (mục 5.3) |

## 2. Hệ quả của việc bỏ cờ internet: hàng rào SSRF thành lớp chặn duy nhất

Hôm nay cờ tắt là thứ duy nhất ngăn agent ra ngoài. Bỏ cờ thì `web_fetch` là một đường ra thật: agent bị jailbreak có thể bảo
nó gọi cổng quản trị của chính agent, cổng API CRM trong mạng Docker, hay `169.254.169.254`. Luật L1–L5 vẫn nguyên, và thêm:

- **T5** trong `apps/agent/tests/test_crm_boundary.py`: `web_fetch` từ chối `localhost`, `127.0.0.1`, `10.*`, `172.16–31.*`,
  `192.168.*`, `169.254.169.254`, IPv6 nội bộ và địa chỉ IPv4 ánh xạ, tên host trong mạng Docker (`api`, `db`, `agent`), host
  phân giải ra IP nội bộ, và URL chuyển hướng sang IP nội bộ. Test đỏ thì không merge.
- Rủi ro còn lại, ghi rõ: agent đọc tài liệu kho tri thức rồi nhét vào URL gửi ra ngoài. Giảm bằng: `web_fetch` chỉ GET, URL
  tối đa 2000 ký tự, không gửi header hay cookie. Không loại bỏ được hẳn nếu tool ra internet.
- Gỡ phần cũ: `ToolSpec.network`, `allow_internet` trong `profile.py`, `assembly.py`, `runtime.py`, `plugins/host.py` (hai chỗ),
  hai test trong `test_plugin_runtime.py`, ghi chú trong `agents/*/agent.toml`.
- Dòng "Không tra cứu trên internet" trong `agents/clinic/AGENTS.md` đổi cho khớp khi `web_*` được bật.

## 2b. Cài đặt agent lên DB + UI (trước tool web)

### Chuyển và giữ lại

| Chuyển lên DB + UI (DB thắng, TOML/tệp chỉ là mặc định lúc mới cài) | Giữ trong TOML (đi qua git, có người duyệt) |
|---|---|
| bật/tắt **từng tool**: tool lõi (`get_datetime`, `memory`, `web_*`) và tool của plugin (`kb_*`, `skill_*`, `scenario_search`) | `name` (khóa của mọi dòng trong DB) |
| `timezone`, `failure_reply` | `[guards]` (quét injection, che bí mật, trần tool mỗi bước) |
| `[agent.variables]` (`clinic_name`, `hotline`) | `[loop]` (trần bước, token, thời gian, gom tin) |
| `[memory]`: bật, `agent_chars`, `user_chars` | `[context]` (cửa sổ token, ngưỡng nén) |
| nội dung `SOUL.md` (vai trò) và `AGENTS.md` (quy tắc) | `[prompt] sections` (cấu trúc prompt, kỹ thuật) |
| (đã có từ trước) `[model]` → trang Model; `[plugins]` → trang Plugin | |

`web_search`, `web_fetch` mặc định **tắt**: chỉ bật bằng trang Công cụ. Vai trò/quy tắc của plugin `skills` (theo kênh, theo tài khoản)
vẫn cộng thêm như hôm nay; ô "Vai trò" và "Quy tắc" ở đây là phần gốc của agent, thay cho hai tệp.

### Thiết kế
- Bảng `agent_rt.agent_settings` (revision Alembic `0002` + `.sql`, quyền cho `agent_rt_app`), một dòng mỗi `(tenant_id, agent)`, mỗi
  cột rỗng = dùng mặc định: `timezone`, `failure_reply`, `variables jsonb`, `persona`, `rules`, `memory_enabled`, `memory_agent_chars`,
  `memory_user_chars`, `tools jsonb` (`{"web_fetch": true, "skill_write": false}`; tool không có trong map theo mặc định), `version`,
  `updated_at`, `updated_by`. CHECK độ dài và miền giá trị như `agent_model_settings`. Cùng mẫu với `model_settings.py`: kho in-memory
  cho test, kho Postgres, `resolve` từng trường "DB > profile".
- Áp ngay không khởi động lại: lưu xong thì `LiveAgent` dựng lại agent (cùng đường plugin đổi đang dùng). Tool lọc sau khi gom tool lõi
  + plugin trong `build_agent`. `failure_reply` hôm nay được đọc một lần lúc dựng `ChannelHub` → đổi sang đọc qua hàm mỗi lần dùng.
  Biến `{{...}}` hôm nay thay lúc `load_profile` → dời sang lúc dựng agent để biến và nội dung sửa trên UI đều được thay.
- API admin (chỉ admin, như trang Model): `GET/PUT /v1/admin/settings` (có `version` chống ghi đè lẫn nhau, trả cả giá trị mặc định
  để UI hiện "đang dùng mặc định") và `GET/PUT /v1/admin/tools` (mọi tool agent đang có: tên, mô tả, nguồn lõi/plugin, bật). CLI:
  `agent settings show|set`, `agent tools list|enable|disable`. Kiểm đầu vào ở server (độ dài, múi giờ có thật, tool có tồn tại).
- UI trong `pema-agent/frontend` (cạnh `components/agent/pages/model-page.tsx`, route `/admin/agent/...`): trang **"Cài đặt"**
  (múi giờ, câu khi lỗi, biến, nhớ, vai trò, quy tắc) và trang **"Công cụ"** (danh sách + công tắc). Làm bằng subagent
  `pema-ui-builder`, cập nhật mock + `contract.test.ts`, `pnpm gen:types`, ghi `web-design-changes.md`. Hai trang này không có màn trên
  canvas cũ: nói rõ trong báo cáo.
- TOML và hai tệp `.md` giữ nguyên làm mặc định; profile `dev` (không có DB) vẫn chạy như cũ.

### Rủi ro
- Admin trên UI giờ sửa được vai trò/quy tắc và bật tool internet: ai có quyền admin (chủ, quản lý qua SSO) là đổi được hành vi agent
  với khách. Mỗi lần lưu ghi `updated_by` + thời điểm; chưa có lịch sử từng phiên bản (để sau).
- Tắt `memory` trên UI bỏ cả tool và phần nhớ trong prompt (cùng một cờ `memory_enabled`).

## 2c. Đề xuất thêm cho phần bảo mật của bước 1 (GHI ĐỂ XEM XÉT, chưa làm)

Bước 1 đã làm đúng như mục 2 và 3 (`netguard.py`, `untrusted.py` trong `agentcore/harness/tools/builtin/`, T5 trong
`test_crm_boundary.py`, luật L6). Các mục dưới đây là chỗ còn thiếu hoặc nên cân nhắc; chủ chọn mục nào thì làm mục đó.

### A. Chỗ thủng đã đo được trong bản đã làm (nên vá, rẻ)
1. **NAT64 và 6to4 bị coi là công khai.** `ipaddress.is_global` trả `True` cho `64:ff9b::7f00:1` (che 127.0.0.1) và `2002:7f00:1::`
   (6to4 che 127.0.0.1), và cho multicast `224.0.0.1`. Kẻ tấn công dựng được một tên miền trỏ AAAA vào dạng này; có đi được tới địa chỉ
   nội bộ hay không còn tùy mạng có cổng NAT64/6to4, hiếm trong Docker nhưng không loại trừ. Vá: tự viết danh sách chặn (`64:ff9b::/96`,
   `2002::/16`, Teredo `2001::/32`, multicast, lấy IPv4 ra khỏi IPv6 che trước khi kiểm). Thêm vào T5.
2. **Chỉ cần MỘT địa chỉ công khai là đi.** Tên miền trả cả IP công khai lẫn nội bộ: hiện code chỉ nối tới IP công khai (không bao giờ
   nối tới IP nội bộ), nên an toàn; nhưng có thể chọn "từ chối nếu bất kỳ IP nào là nội bộ" để phát hiện sớm tên miền đáng ngờ.
3. **Chưa giới hạn cổng và userinfo.** Cổng nào cũng đi (nếu tới được một IP công khai), `http://user:pass@host` cũng đi. Vá: chỉ 80 và
   443, từ chối URL có `user:pass@`.
4. **Chưa lọc loại nội dung.** Mới cắt theo byte; `web_fetch` (bước 2) nên chỉ nhận HTML, văn bản, JSON, XML và từ chối nhị phân.
5. **Chưa có trần số lần gọi.** Ai nhắn Zalo cũng có thể bắt agent tải hàng loạt URL (quét, đánh vào site khác, tốn băng thông). Vá:
   tối đa N lần mỗi lượt, M lần mỗi cuộc chat mỗi giờ, và trần đồng thời toàn hệ thống (hằng số trong code).
6. **Log:** chỉ ghi tên host, không ghi cả URL (có thể chứa dữ liệu bơm ra).
7. **Hiện chỉ tin vào kiểm tra khi kết nối + kiểm trước mỗi chặng.** Không có tầng thứ hai ở mạng (xem C).

### B. Chặn ghi sau khi đọc web (rủi ro prompt injection, chưa có trong kế hoạch)
Một trang web độc có thể ra lệnh cho agent gọi `memory`, `skill_write`, `skill_patch` để ghi đè vai trò hoặc nhớ lệnh lâu dài. `untrusted`
chỉ giảm, không chặn được model làm theo lệnh ẩn; `injection_guard` hiện chỉ chặn theo mẫu từ, dễ lách. Đề xuất: một `PreToolHook`: khi
lượt đã gọi `web_fetch` hoặc `web_search`, từ chối ba tool ghi đó trong phần còn lại của lượt. Khung hook có sẵn
(`agentcore.harness.hooks`), việc nhỏ. Quy tắc "không cổng chặn tool" của bản demo là về xác thực người dùng, không phải về nội dung ngoài.

### C. Danh sách tên miền cho phép / chặn (đã bỏ khỏi kế hoạch, nên cân nhắc lại)
Rủi ro còn lại lớn nhất của tool ra internet là bơm dữ liệu ra ngoài: agent bị lừa đọc tài liệu kho tri thức rồi nhét vào query string của
một URL. Giới hạn độ dài URL chỉ làm chậm. Một danh sách tên miền cho phép (rỗng = mọi tên miền công khai) giảm thật; cần một chỗ cài
đặt (trang "Cài đặt" của bước 0b là nơi hợp lý).

### D. Chặn ở tầng mạng Docker (việc hạ tầng, chưa có trong kế hoạch)
`netguard` chỉ là chặn ở tầng ứng dụng. Container agent nằm chung mạng với `api`, `db`, `redis`. Muốn chắc hơn: luật egress chặn container
agent ra các dải riêng ngoại trừ `db` và `api:8000/.well-known`, hoặc một proxy đi ra ngoài là đường duy nhất ra internet. Cần trước khi có
bệnh nhân thật (cũng ghi trong handoff, rủi ro 5 và 6).

### Ghi chú bước 2 (đã làm, `web_search` và `web_fetch`)
- Hai tool nằm trong danh mục tool lõi (`builtin_tools()`), **mặc định tắt**: bật trên trang "Công cụ" hoặc `agent tools enable web_fetch`.
- `web_search` dùng DuckDuckGo bằng **POST form** (GET bị trả trang thử thách); vì vậy `netguard.fetch` có tham số `form` (chỉ lượt đầu
  là POST, chuyển hướng sau đó là GET; `web_fetch` không bao giờ dùng `form`).
- `web_fetch` đã có thêm so với kế hoạch: từ chối nội dung không phải văn bản (ảnh, PDF, nhị phân), mã HTTP ≥ 400 báo lỗi, đọc đúng
  charset khai trong header, phân tích HTML ngoài vòng sự kiện (`asyncio.to_thread`). Tên miền không phân giải được là một lần tải bị
  từ chối, không phải lỗi sập.
- Kết quả được cắt TRƯỚC khi bọc và `max_result_chars` của tool chừa 1000 ký tự cho khung, để executor không cắt mất thẻ đóng; chuỗi
  thay thế thẻ giả ngắn hơn thẻ thật nên văn bản bọc không bao giờ dài hơn khung + văn bản.
- Rủi ro riêng của `web_search`: bóc HTML của DuckDuckGo (selector `result__a`, `result__snippet`) sẽ hỏng khi họ đổi giao diện hoặc
  hiện thử thách chống bot; khi đó tool báo "No results" chứ không sập. Chưa có nhà cung cấp dự phòng (đã bỏ Brave theo quyết định).
- Chưa lọc menu dài theo mật độ liên kết (chỉ bỏ nav/header/footer/aside); thêm nếu trang chỉ ra menu cho model.

### Đã kiểm trong bước 1
- `netguard` chạy thật với TLS qua kết nối ghim địa chỉ (`https://example.com/` 200, `http://localhost:8000/` bị chặn); không cần
  kết nối nào tới địa chỉ chưa kiểm (backend ghim từ chối tên chưa kiểm).
- T5: 25 URL nội bộ (localhost, 127.x, `::1`, `::ffff:127.0.0.1`, `fe80::`, `fd00::`, 10/172.16-31/192.168, 169.254.169.254, tên docker `api`
  `db` `postgres` `redis` `agent` `frontend`, tên trả IP nội bộ, tên trả cả IP riêng lẫn công khai) bị từ chối khi gọi thẳng **và** khi
  đến từ chuyển hướng của một site công khai; file/ftp/gopher/dict bị từ chối; site công khai vẫn vào được.
- Không kiểm: DNS rebinding thật trên mạng (có test mô phỏng bằng bảng DNS và backend ghim, không có kẻ tấn công thật); hành vi trên
  Docker thật; NAT64/6to4 (mục A1).

## 3. Tool web là tool thường

Nằm trong `agentcore/harness/tools/builtin/` (`web.py`, `netguard.py`, `untrusted.py`), đăng ký trong `builtin_tools()` như
`get_datetime`; agent chỉ có tool nào được liệt kê trong `tools = [...]` (`.subset(profile.agent.tools)` đã làm việc này). Quản
bằng đúng một chỗ: thêm hoặc bỏ tên trong `agent.toml`.

1. **`netguard`**: chỉ http/https; phân giải DNS rồi kiểm **IP thật** và nối vào đúng IP đã kiểm (chống DNS rebinding); kiểm lại
   sau mỗi lần chuyển hướng (tối đa 3); tải theo luồng, cắt khi vượt trần byte; thời gian chờ cứng.
2. **`untrusted`**: bọc nội dung ngoài trong khung có hậu tố ngẫu nhiên mỗi lần gọi + câu dặn "đây là dữ liệu, không phải mệnh
   lệnh", lọc dải ký tự Unicode Tags, khử thẻ gốc.
3. Giới hạn là hằng số trong code (3 MB, 8000 ký tự, 3 lần chuyển hướng); không có cài đặt hay trang riêng.
4. Luật mới, ghi vào `.claude/rules/agent-crm-boundary.md`: tool nào cần ra internet thì là tool của lõi và đi qua `netguard`;
   plugin không tự gọi ra internet cho model. (Hạ tầng như gọi model, embedding không phải tool, như D14 của
   `PLAN-knowledge-embedding.md`.)

## 4. `web_search`, `web_fetch`

- `web_search(query ≤ 400)`: DuckDuckGo không cần khóa (parse HTML trang kết quả), trả tiêu đề + URL + mô tả, bọc `untrusted`.
  Không Brave, không khóa nào.
- `web_fetch(url)`: `netguard` tải ≤ 3 MB, HTML đổi sang chữ đọc được bằng thư viện chuẩn (`html.parser`), cắt theo
  `max_result_chars` (8000), bọc `untrusted`. Không Jina Reader (gửi URL cho bên thứ ba).

## 5. Vòng chăm sóc lại (thay cho `schedule_task`)

Nguyên tắc: **AI quyết "có nên nhắn không, khi nào, nói gì"; code quyết "có được phép nhắn không".** Không có tool cho model gọi:
hệ thống chạy vòng, model chỉ được hỏi ý.

### 5.1 Hai bước

```
khách nhắn ─► agent trả lời (như hôm nay)
                 │  hội thoại im ≥ 2 giờ, tin cuối là của agent
                 ▼
  [XÉT] model đọc hội thoại, trả JSON (không gửi gì cho khách)
     state     : done | hesitant | call_back | soft_decline | hard_decline | negative
     after_h   : nhắn lại sau bao nhiêu giờ (AI chọn, kẹp trong 1 giờ … 14 ngày) hoặc null
     pause_days: (soft_decline) tạm ngưng bao nhiêu ngày
     reason    : một câu cho nhân viên đọc
                 │
   soft_decline ─► danh sách ngưng: tạm ngưng pause_days
   hard_decline / negative ─► danh sách ngưng: ngưng hẳn
   hesitant / call_back ─► hẹn giờ nhắn lại
   done ─► không làm gì
                 ▼  đến giờ
  [LÀM] code kiểm lại: khách đã nhắn chưa? trong giờ cho phép? chưa vượt trần? không bị ngưng?
     → chạy một lượt agent với chỉ dẫn nội bộ "nhắn lại tự nhiên theo mạch cũ, hoặc trả SKIP"
     → gửi qua kênh, đánh dấu tin chủ động (kill-switch và trần ngày của bridge áp dụng)
     → khách vẫn im: lần sau xét lại; 2 lần liền không trả lời thì tự ngưng
```

- "Từ chối khéo" kiểu Việt ("để em suy nghĩ thêm", "dạo này em bận", "chắc để sau") là việc của câu hỏi ở bước XÉT: prompt có
  ví dụ tiếng Việt cho từng `state`, model trả JSON theo lược đồ pydantic; JSON hỏng thì coi là `done` (không nhắn).
- Khách nói "thứ sáu nhắn lại em nhé" thì XÉT ra `call_back` và tự đặt giờ: không cần lịch cố định.
- Khách nhắn bất cứ lúc nào thì hẹn đang chờ bị hủy; lần im sau được xét lại từ đầu. Khách tự nhắn lại sau khi bị "ngưng hẳn"
  thì gỡ khỏi danh sách ngưng (khách chủ động mở lại).

### 5.2 Lưu và chạy

- Bảng `agent_rt.follow_ups` (revision Alembic mới `0003` + `.sql`, quyền cho `agent_rt_app`): khóa `(tenant, agent, kênh,
  conversation_id)`, `state`, `reason`, `next_at`, `paused_until`, `stopped`, `unanswered` (số lần nhắn liền chưa được trả lời),
  `last_sent_at`, `reviewed_through` (id tin cuối đã xét, để mỗi lần im chỉ xét một lần), `updated_at`. Bảng này cũng là
  danh sách ngưng.
- Vòng nền của app (`agent_app/follow_up.py`, khởi động cạnh `ChannelHub` trong `runtime.py`), mỗi 60 giây:
  tìm hội thoại cần XÉT (lấy giờ tin cuối từ ingress) và hẹn đến giờ LÀM, khóa bằng `FOR UPDATE SKIP LOCKED`.
- Bước LÀM đưa một tin nội bộ vào ingress (`message_id = followup:<id>:<lần>`, chống chạy đúp) để lượt chạy, trả lời và gửi
  đi đúng đường hiện có. Chỉ dẫn nội bộ không lưu thành tin của khách. Tin mang `metadata["proactive"] = "1"`; adapter Zalo
  cá nhân đọc khóa này để gửi với cờ `proactive` của bridge. Kiểm ở bước 3: cửa nào của ingress/dispatcher hợp để đưa tin
  nội bộ vào mà không lẫn với tin thật.
- Agent trả `SKIP` hoặc rỗng thì không gửi, ghi `reason`.

### 5.3 Khung cứng (code, AI không vượt được)

| Luật | Mặc định |
|---|---|
| Bật | tắt; bật và chọn kênh trên trang "Cài đặt" (cột mới của `agent_settings`), không qua TOML |
| Kênh | chỉ Zalo cá nhân, chỉ chat 1-1 do khách nhắn trước; không nhóm |
| Xét sau khi im | 2 giờ, tin cuối là của agent |
| Giờ được nhắn | 8:00–20:00 giờ Việt Nam; hẹn rơi ngoài khung thì dời sang 8:00 hôm sau |
| Khoảng cách tối thiểu | 24 giờ giữa hai lần nhắn |
| Trần | 2 lần nhắn liền không được trả lời thì tự ngưng |
| Ngưng hẳn | không bao giờ nhắn lại, trừ khi khách tự nhắn trước |
| Lưới từ khóa | ngoài phán đoán của AI: "đừng nhắn", "không cần nữa", "phiền", "spam", "chặn"... là ngưng hẳn ngay |
| Dữ liệu | chỉ hội thoại trong kho riêng của agent (L4: không tra bệnh nhân, lịch hẹn, đơn bên CRM) |

Chọn từng tài khoản Zalo sẽ làm cùng giao diện (hoãn); trước mắt bật theo kênh.

### 5.4 Rủi ro ghi rõ

- Bước D8 vừa gỡ việc CRM tự gửi tin cho bệnh nhân; vòng này mở lại tin chủ động, nhưng ở phía agent và chỉ với hội thoại
  khách đã tự bắt đầu.
- Tài khoản Zalo cá nhân nhắn chủ động nhiều dễ bị đánh dấu spam; Nghị định 91/2020 về tin nhắn rác đòi khách đồng ý trước khi
  nhận tin quảng cáo. Khung ở 5.3 là để giữ ít; nội dung mang tính quảng cáo thì chủ nên hỏi người hiểu luật.
- Mỗi lần hội thoại im tốn một lời gọi model ở bước XÉT.

### Ghi chú bước 3 (đã làm: nửa XÉT và khung cứng, chưa gửi gì cho khách)
Mã: `agent_app/follow_up.py`; bảng `agent_rt.agent_follow_up` và hai cột `follow_up_enabled`, `follow_up_channels` của `agent_settings`
(migration `0003`); đường quản trị `GET /v1/admin/follow-ups`; bật bằng `agent settings set --follow-up on --follow-up-channel <tên kênh>`
hoặc `PATCH /v1/admin/settings`. **Mặc định tắt, chưa có trang giao diện** (hoãn như đã chốt).
- **Khung cứng** là hàm thuần có test: giờ 8–20 giờ Việt Nam, cách nhau ≥ 24 giờ, chờ 1 giờ–14 ngày, tạm ngưng 1–60 ngày, 2 lần nhắn
  không được trả lời thì tự ngưng, hard_decline/negative là ngưng hẳn, lưới từ khóa (không dấu cũng bắt), `may_send()` để bước 4 hỏi
  trước khi gửi.
- **Chỉ xét** hội thoại 1-1 của các kênh admin chọn, mà tin cuối là câu trả lời của agent đã gửi xong, im ≥ 2 giờ, và **không quá
  1 ngày** (bật vòng không bao giờ lôi khách cũ ra nhắn). Mỗi lượt quét tối đa 10 hội thoại. Mỗi lần im chỉ xét một lần
  (`reviewed_through`); khách nhắn lại thì gỡ ngưng và đếm lại từ đầu.
- Chỉ đọc kho riêng của agent (bảng `agent_ingress` và phiên của chính nó): đúng luật L4, không chạm CRM.
- **Chọn cần chủ xem xét:**
  1. `soft_decline` (từ chối khéo): hiện **cho phép nhắn lại một lần sau khi hết thời gian tạm ngưng** (`next_at` = hết tạm ngưng, rơi vào
     giờ cho phép). Nếu chủ muốn "từ chối khéo thì không bao giờ nhắn lại trừ khi khách nhắn trước", đổi một dòng ở `decide`.
  2. Lưới từ khóa có thể bắt nhầm câu lịch sự ("không cần nữa" trong ngữ cảnh khác): hậu quả chỉ là ngưng nhắn khách đó.
  3. Mỗi hội thoại im tốn một lời gọi model; trần 10 hội thoại mỗi phút.
  4. Truy vấn "im lặng" quét các dòng `agent_ingress` gần đây theo `DISTINCT ON`; đủ cho demo, cần chỉ mục riêng khi bảng lớn.
- **Chưa có (bước 4):** hủy hẹn khi khách nhắn lại trước giờ hẹn, gửi tin, gắn `proactive`, tăng `unanswered`, `last_sent_at`.

## 6. Thứ tự làm (mỗi bước một commit; test theo `.claude/rules/testing.md`)

| Bước | Nội dung | Test chạy |
|---|---|---|
| 0 | Bỏ `allow_internet` và `ToolSpec.network` (**đã làm**, `64e85e15`) | — |
| 0a (**đã làm**) | `agent_settings` (`0002`), kho, resolve, `LiveAgent` dựng lại, lọc tool, `failure_reply` và biến đọc lúc dựng; API + CLI | test mới, `test_agent_app.py`, `test_channel_hub.py`, `test_gateway.py`, profile; test DB chỉ trên `scratch_*` |
| 0b (**đã làm**) | Trang "Cài đặt" và "Công cụ" (`pema-ui-builder`) | `pnpm test`, `contract.test.ts`, `pnpm visual`, `pending-web.cjs` |
| 1 (**đã làm**, đúng kế hoạch) | `netguard`, `untrusted` + T5 | test mới + `test_crm_boundary.py` |
| 2 (**đã làm**) | `web_search`, `web_fetch` (trang giả, không gọi mạng thật) | test mới |
| 3 (**đã làm**) | Vòng chăm sóc lại: bảng `0003`, bước XÉT (model giả), khung cứng | test mới (luật khung là hàm thuần, test kỹ nhất) |
| 4 | Bước LÀM: đưa tin nội bộ vào ingress, `proactive` ở Zalo cá nhân | test mới, `tests/zalo/*`, `test_dispatcher*`, `test_channel_hub.py`; test DB chỉ trên cơ sở `scratch_*` hoặc container tạm |
| 5 | Bật `web_search`, `web_fetch` trên trang Công cụ (nếu chủ muốn) và chăm sóc lại trên trang Cài đặt theo ý chủ; sửa `AGENTS.md`; cập nhật `GUIDE-agent-harness.md`, bản ghi `project-agent-tool-rule` | chạy thử profile |

Sau mỗi bước chạy lại T1, T3, T4, T5 (`.claude/rules/agent-crm-boundary.md`). Bước 0a, 3–4 đụng migration nên không chạm cơ sở demo
`pema` hay `pema_agent` đang chạy.

## 7. Không làm (lần này)

Giao diện danh sách chăm sóc lại / ngưng và chọn theo từng tài khoản Zalo (hoãn); nhận biết nhân viên đã tự nhắn tay cho khách
từ máy khác (`origin="own"`) để vòng lùi lại (hoãn, chưa kiểm dữ liệu); `schedule_task`; các tool đã bỏ ở mục 1; khóa Brave,
Jina Reader; `get_group_info` / `tag_member` / `add_reaction`; tool MCP; bất kỳ tool nào chạm bệnh nhân/lịch hẹn/đơn/tài chính (L4).
