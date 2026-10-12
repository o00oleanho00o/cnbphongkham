# Plan: bước 0 của RAG, phần lõi cho plugin `knowledge`

Trạng thái: **đã duyệt (3 câu hỏi đã trả lời, mục 5), chưa code** (viết 2026-10-12, nhánh `feat/knowledge-ui`). Là bước 0 ở bảng 19.4
của [PLAN-knowledge-plugin.md](PLAN-knowledge-plugin.md): `register_migrations`, `ctx.model`, `ToolOutput.detail`, ngữ
cảnh tin cậy theo lượt, `max_steps` 10. Phần `Contribution.section` của SDK đã làm cùng UI Kho tri thức nên không nằm ở đây.

Mục tiêu: sau bước này lõi có đủ chỗ cắm cho plugin `knowledge`. Plugin cần tạo bảng riêng, gọi model trong danh sách, ghi
số liệu tìm kiếm vào trace và biết "hôm nay là ngày nào, khách đã xác thực chưa" mà không tin lời khách. Bước này **chưa có
tính năng người dùng thấy**: mọi thứ cũ chạy như cũ và được chứng minh bằng test.

## 1. Đã đọc trong mã (để plan khớp thực tế)

| Chỗ | Hiện tại |
|---|---|
| `agentcore/harness/tools/spec.py` | `ToolContext(session_id, tenant_id, user_id, channel)`: kênh **đã có**. `ToolOutput(text, is_error)`. |
| `agentcore/harness/tools/executor.py` | `ToolRun(result, duration_s, blocked_by)`; chỉ chép `output.text` vào kết quả. |
| `agentcore/loop/run_turn.py` | `run_turn(..., tenant_id, user_id, channel, clock, ...)` tạo `ToolContext` một lần mỗi lượt. `_tool_event` ghi `detail = {call_id, result_chars, blocked_by}` cố định. |
| `agentcore/prompt/sections.py`, `builtin.py` | `TurnInfo(now, channel)`; section lượt `environment` đã in ngày giờ. |
| `agent_app/dispatcher.py`, `cli.py`, `replay.py` | 3 nơi gọi `run_turn`. Kênh và HTTP đi qua dispatcher (bản ghi ingress trong DB). |
| `agent_app/gateway.py` | `ChatRequest` có `extra="forbid"`: khách hay hệ thống ngoài không nhét thêm trường được. |
| `agent_app/plugins/host.py` | `PluginContext`: `storage` (JSON), `data_dir`, `encrypt/decrypt`, `register_tool/section/hook/channel/routes`. Chưa có model, chưa có bảng riêng. |
| `agent_app/plugins/manifest.py` | `plugin.toml`: `requires_env`, `ui`, `user_config`… |
| `agent_app/model_settings.py` | `DynamicModel` (model đang dùng, tự dựng lại khi cài đặt đổi), `ModelAdmin` + `ModelEntryStore` (danh sách model, khóa đã niêm phong). |
| Migration | Compose: service `migrate` chạy `agent db bootstrap-role && alembic upgrade head` bằng role chủ (`AGENT_MIGRATION_DATABASE_URL`). Service chạy bằng `agent_rt_app`, không có quyền DDL. Makefile `db-upgrade`. |
| Profile | `agents/clinic/agent.toml` và `agents/dev/agent.toml`: `max_steps = 6` (giới hạn 1–50). |

## 2. Năm việc

### 0.1 `ToolOutput.detail`: tool ghi số liệu vào trace (nhỏ nhất, làm trước)

- `ToolOutput` thêm `detail: dict[str, JsonValue] = {}`. Không vào lịch sử chat, model không thấy; chỉ vào trace.
- `ToolRun` thêm `detail`; executor chép từ `ToolOutput`. Tool lỗi, tool bị chặn, quá giờ thì `detail` rỗng.
- `_tool_event` đặt nó dưới khóa riêng `detail["tool"] = ...` để tool không ghi đè được `call_id`, `blocked_by` của lõi.
- Trần: JSON tối đa 2.000 ký tự, quá thì thay bằng `{"truncated": true, "chars": n}` (trace phải nhỏ). Khóa và giá trị
  phải dựng được thành JSON, kiểm khi tạo `ToolOutput` (pydantic).
- Trang Trace (clinic web) đã in "metadata" của một bước. Kiểm xem nó in được dict lồng không; không được thì sửa nhỏ cách
  hiển thị (ghi log thay đổi hiển thị).
- `kb_search` sau này ghi: số ứng viên từng nhánh, có nới lọc không, điểm cao nhất, `doc_id` trả về. Chính nhờ cái này mà
  bộ đo lấy `retrieved_doc_ids` từ trace thay vì tin model tự khai (plan RAG 19.3 mục 8).

### 0.2 Thời điểm của lượt và ngữ cảnh tin cậy (phương án B, user chốt 2026-10-12)

Ngữ cảnh tin cậy là những điều **hệ thống** biết về lượt chat, không phải điều khách tự nói: ngày hỏi, khách đã xác thực
chưa, đã xác nhận chưa, vài sự thật khác. Nó đi vào `ToolContext` và một section lượt ngắn, **không bao giờ** đọc từ nội
dung tin nhắn hay tài liệu.

- `ToolContext` thêm `now: datetime | None`: lúc bắt đầu lượt, có múi giờ, do `run_turn` đặt từ `clock()`. `kb_search` dùng
  nó làm "ngày hỏi" (`as_of`) để lọc hiệu lực tài liệu. Bộ đo muốn hỏi "như ngày 15/09" thì truyền `clock` cố định cho
  ca đó; `run_turn` đã nhận `clock`, nên **không cần trường `as_of` riêng** và ngày trong prompt cũng khớp luôn.
- `TrustedContext` mới trong `agentcore` (dataclass bất biến):
  - `identity_verified: bool = False`, `confirmed: bool = False`;
  - `facts: Mapping[str, str] = {}`: vài dòng sự thật do hệ thống đặt (chi nhánh, tên hiển thị kênh…), trần 10 dòng × 200
    ký tự;
  - `mock_tool_results: Mapping[str, JsonValue] = {}`: chỉ cho bộ đo (plugin giả lập `may_demo` đọc).
- `run_turn(..., trusted: TrustedContext | None = None)` → `ToolContext.trusted` và `TurnInfo.trusted`. Section lượt
  `trusted` (builtin) in vài dòng khi có, không in gì khi rỗng. Nằm ở khối ngữ cảnh của lượt như `environment`, nên
  **không phá cache** của system prompt.
- **Ai đặt được (phương án B):**
  1. Mã trong tiến trình: runner bộ đo, `replay`, CLI (cờ `--verified`, `--confirmed`, `--fact k=v`).
  2. HTTP: `ChatRequest` thêm trường tùy chọn `context: {identity_verified, confirmed, facts}`. Mọi người gọi đã qua xác
     thực của gateway (SSO của clinic web, khóa API) đều đặt được. `mock_tool_results` **không** nhận qua HTTP.
  3. Kênh: `InboundMessage` thêm `trusted: TrustedContext | None`; adapter của kênh (Zalo…) tự điền khi nó biết chắc điều
     gì đó. Ở bước 0 Zalo chưa điền gì; chỉ mở chỗ.
  - Đường đi: bản ghi ingress thêm cột `trusted` (JSON, alembic `0012_ingress_trusted`), dispatcher đọc ra và truyền vào
    `run_turn`. Gộp nhiều tin một lượt (collect/steer) thì dùng của tin đầu.
- `tenant_id` đã là tham số của `run_turn` và đã vào `ToolContext`: giữ nguyên, bộ lọc tenant của `kb_search` dùng nó.

Ghi chú 2026-10-12: kho tri thức dùng chung cho mọi kênh (không chia Bệnh nhân / Nội bộ), xem PLAN-knowledge-ui.md
mục 10. `ToolContext.channel` vẫn có nhưng `kb_search` không dùng nó để lọc.

### 0.2b Quy tắc dùng tool (user chốt 2026-10-12, **agent khác đọc kỹ mục này**)

**Agent được gọi mọi tool trong hệ thống, tùy ý. Chỉ cấm ra Internet.**

- Lõi **không** chặn tool nào vì "khách chưa xác thực" hay "chưa xác nhận". `identity_verified` và `confirmed` chỉ là
  thông tin cho agent biết, **không phải cổng chặn**. Không viết hook hay điều kiện trong tool kiểu "chưa xác thực thì từ
  chối". Thủ tục hỏi xác nhận trước khi hủy lịch… (nếu muốn) chỉ nằm trong prompt, không trong mã.
- Mọi tool của lõi và của plugin (tra kho tri thức, đặt/hủy lịch giả lập, hồ sơ, bộ nhớ, kỹ năng, `calculate`…) đều bật
  cho agent clinic, không có danh sách cho phép từng tool.
- **Cấm duy nhất: tool ra Internet** (tìm web, đọc URL, gọi API công khai theo yêu cầu của model). Cách giữ bằng mã:
  - `ToolSpec` thêm `network: Literal["internal", "internet"] = "internal"`. Tool nào gọi ra ngoài mạng nội bộ của hệ
    thống phải khai `"internet"`.
  - Profile thêm `[tools] allow_internet = false` (mặc định false, clinic false). Lõi **từ chối đăng ký** tool `internet`
    khi cờ tắt: tool của lõi thì lỗi lúc dựng agent, tool của plugin thì plugin vào trạng thái lỗi với câu rõ ràng.
  - Kênh (Zalo nói chuyện với máy chủ Zalo) không phải tool, không bị cấm. Plugin `knowledge` gọi embedding qua
    gateway Beeknoee là việc của plugin lúc nạp/tìm, không phải tool "tra mạng" theo ý model, nên được phép.
  - `AGENTS.md` của clinic thêm một dòng: "Không tra cứu trên Internet; chỉ dùng tài liệu và công cụ trong hệ thống."
- Giữ nguyên (không phải cổng chặn tool hợp lệ): guard chống lặp, giới hạn số tool mỗi bước, quét chèn lệnh
  (`injection_scan`), che bí mật (`redact_secrets`), `disabled_tools` từng tài khoản Zalo (do admin tự tắt).
- **Rủi ro đã biết và chấp nhận cho demo:** ai nhắn Zalo cũng có thể khiến agent gọi bất kỳ tool nào trong hệ thống (ví dụ
  xem hay hủy lịch của người khác khi đã có tool thật). Trước khi chạy với bệnh nhân thật phải xem lại mục này, cùng với việc
  bật lại che dữ liệu trước khi embedding.

### 0.3 `ctx.model(entry_id=None)`: plugin gọi model mà không cầm khóa

- `PluginContext.model(entry_id: str | None = None) -> ModelClient`.
  - `None`: chính model agent đang dùng (`DynamicModel`), đổi model ở trang Model thì plugin cũng đổi theo.
  - Mã một mục trong danh sách model: client dựng từ mục đó (khóa giải niêm phong trong lõi). Cache theo `(id, phiên bản)`,
    sửa mục thì dựng lại. Mục bị xóa → lỗi đọc được "Model <id> không còn trong danh sách" (plugin bắt và lùi về model đang
    dùng hoặc báo trong Cài đặt).
- Host nhận một hàm `models(entry_id) -> ModelClient` từ `runtime.py` (nơi đã có `DynamicModel` và kho mục). Plugin không
  thấy khóa, không thấy `ModelAdmin`.
- Ghi nhật ký mỗi lần gọi theo tên plugin (không nội dung). Token plugin dùng **chưa** vào số liệu "Token hôm nay" của
  Tổng quan: ghi là việc sau (cần bảng usage riêng, không đụng trace của lượt chat).
- Trang Cài đặt của Kho tri thức đã có ô chọn "Model đang chọn / một mục trong danh sách": lưu `entry_id`, plugin gọi
  `ctx.model(entry_id)`.

### 0.4 Migration của plugin

Đề nghị **đổi nhỏ so với plan RAG**: khai báo trong `plugin.toml` thay vì `ctx.register_migrations(folder)`.

```toml
[migrations]
dir = "migrations"   # 0001_tao_bang.sql, 0002_...
```

Lý do: lệnh migrate chạy lúc triển khai, trước khi service chạy và không nạp mã plugin. Đọc manifest thì biết thư mục
mà không phải gọi `register()` của plugin (có khi plugin còn tắt).

- Bảng mới `agent_rt.plugin_migration(plugin, version, name, checksum, applied_at)`, tạo bằng một alembic revision
  của agent (`0013_plugin_migrations`). Role `agent_rt_app` chỉ được SELECT.
- Lệnh `agent db migrate-plugins` (role chủ, `AGENT_MIGRATION_DATABASE_URL`). Duyệt mọi plugin có sẵn và cài thêm, kể cả
  đang tắt. Với mỗi tệp `NNNN_*.sql` chưa chạy:
  1. chạy cả tệp trong **một giao dịch**;
  2. ghi phiên bản và checksum;
  3. cấp `SELECT, INSERT, UPDATE, DELETE` trên các bảng plugin vừa tạo (và `USAGE` trên sequence) cho `agent_rt_app`.
- Chỉ đi tiến, không có bản lùi.
- Tệp đã chạy mà bị sửa (checksum khác) → dừng với lỗi rõ, không chạy tiếp.
- Tên bảng phải có tiền tố của plugin (`kb_` cho `knowledge`). Lệnh từ chối tệp tạo bảng ngoài tiền tố: kiểm đơn giản
  bằng regex `CREATE TABLE`, đủ cho plugin có sẵn.
- Compose: service `migrate` thành `agent db bootstrap-role && alembic upgrade head && agent db migrate-plugins`.
  Makefile `db-upgrade` cũng thêm bước này.
- Lúc nạp plugin (host): plugin có `[migrations]` mà DB thiếu phiên bản mới nhất → plugin vào trạng thái lỗi với câu
  "Chưa chạy migration của plugin (agent db migrate-plugins)". Trang Plugins hiện ngay câu đó, service vẫn chạy cho các
  plugin khác. Chạy không có DB (kho trong bộ nhớ) thì plugin có migration báo "cần Postgres".
- `pgvector` (bước 4) cần `CREATE EXTENSION vector`: tệp migration của plugin chạy bằng role chủ nên làm được, nhưng
  image Postgres phải có pgvector. Kiểm ở bước 4, không phải bây giờ.

### 0.5 Profile

- `agents/clinic/agent.toml`: `max_steps` 6 → **10** (3 lượt tìm + 1 đọc + trả lời vẫn dư). Guard chống lặp sẵn có chặn
  gọi `kb_search` cùng tham số nhiều lần.
- `agents/dev/agent.toml`: giữ 6 (xem câu hỏi 2).
- Chưa thêm `knowledge` vào `plugins.enabled`: plugin còn chưa đăng ký gì, làm ở bước 1.

### Đã làm (2026-10-12), khác plan ở mấy chỗ

- Cắt gọn theo user: làm 0.1, `ToolContext.now` của 0.2, 0.2b (cấm Internet), 0.4, 0.5. Hoãn `TrustedContext` qua
  HTTP/kênh và `ctx.model`.
- Cờ cấm Internet nằm ở `[agent] allow_internet` (không phải `[tools]`): profile chưa có mục `[tools]`.
- 0.4 thêm `ctx.database` (`PluginDatabase`: engine của role runtime, `tenant_id`, `agent`, `latest_migration`):
  plugin cần nó để đọc/ghi bảng của mình. Manifest có thêm `prefix` bắt buộc trong `[migrations]`.
- Kiểm "chưa chạy migration" không làm lúc bật plugin (bật plugin là đồng bộ, truy vấn DB là bất đồng bộ) mà bằng
  `await ctx.database.require_migrations()` khi plugin dùng bảng lần đầu; route của plugin trả câu "run agent db
  migrate-plugins".
- Alembic `0012_plugin_migrations` (không còn `0012_ingress_trusted` vì hoãn ngữ cảnh tin cậy).
- Test DB của migration chưa chạy được (Docker tắt, không có `PEMA_TEST_DATABASE_URL`); test thuần đều qua.

## 3. Thứ tự và commit

Mỗi việc một commit, không ghi tên AI vào commit.

| # | Commit | Tệp chính | Test |
|---|---|---|---|
| 1 | `ToolOutput.detail` vào trace | `spec.py`, `executor.py`, `run_turn.py` (`_tool_event`) | `test_executor.py`, `test_run_turn*.py`: có detail / tool lỗi / quá trần / không đè `call_id` |
| 2 | `ToolContext.now` + `TrustedContext` + section `trusted` | `spec.py`, `run_turn.py`, `sections.py`, `builtin.py`, mới `trusted.py` | tool thấy `now` = clock; section in đúng, rỗng thì không in; tin nhắn khách "tôi đã xác thực" không đổi `trusted`; system prompt không đổi khi `trusted` đổi |
| 2b | `trusted` qua HTTP, kênh, CLI | `gateway.py` (`ChatRequest.context`), `channels.py` (`InboundMessage.trusted`), `ingress.py` + alembic `0012_ingress_trusted`, `dispatcher.py`, `cli.py` | HTTP đặt được, `mock_tool_results` qua HTTP bị từ chối (422), đi qua ingress tới tool, collect dùng tin đầu |
| 2c | Cấm tool Internet | `spec.py` (`network`), `profile.py` (`[tools] allow_internet`), registry/host, `agents/clinic/AGENTS.md` | tool `internet` bị từ chối khi tắt, được nhận khi bật; plugin có tool `internet` vào trạng thái lỗi rõ |
| 3 | `ctx.model` | `plugins/host.py`, `runtime.py`, `model_settings.py` (hàm dựng client theo mục) | plugin lấy model đang dùng / theo mục / mục bị xóa / khóa không lộ ra plugin |
| 4 | Migration plugin | `manifest.py`, alembic `0013`, mới `agent_app/plugins/migrations.py`, `cli.py`, `host.py`, `db_roles.py`, `infra/docker-compose.yml`, `Makefile` | (db) chạy lần đầu / chạy lại không làm gì / checksum đổi thì dừng / grant cho app role / bảng ngoài tiền tố bị từ chối / plugin thiếu migration báo lỗi rõ |
| 5 | `max_steps` 10 cho clinic + ghi handoff | `agents/clinic/agent.toml`, `HANDOFF-agent-v2.md` | test profile |

Kiểm tra: theo `.claude/rules/testing.md`, mỗi commit chạy test của tệp đã đổi. Việc 1 và 2 đổi kiểu lõi dùng khắp nơi
(`ToolContext`, `run_turn`), nên **cuối bước 0 chạy cả bộ test của `agent-core` và `apps/agent`** (kể cả test `db` với
`PEMA_TEST_DATABASE_URL`), cùng `ruff` và `pyright` trên các đường dẫn đã đổi.

Docker: việc 4 đổi lệnh của service `migrate`, cần build lại image agent. Lệnh Docker cần bạn cho phép.

## 4. Không làm ở bước 0

- Tool `kb_search`, bảng `kb_*`, mọi phần của plugin `knowledge` (bước 1).
- Zalo tự điền `trusted` (chỉ mở chỗ ở bước 0).
- Đếm token của plugin vào Tổng quan.
- `register_skill`, lệnh CLI của plugin (plan RAG mục 12, việc 7–8).

## 5. Câu hỏi cần bạn chốt

1. ~~Migration khai báo trong `plugin.toml`?~~ **User đồng ý (2026-10-12).**
2. ~~`max_steps` 10 cho profile nào?~~ **Chỉ clinic (user, 2026-10-12).**
3. ~~Ai đặt ngữ cảnh tin cậy?~~ **Phương án B: cả HTTP và kênh; đồng thời bỏ cổng chặn, agent gọi mọi tool trong hệ
   thống, chỉ cấm ra Internet (user, 2026-10-12). Xem 0.2 và 0.2b.**
