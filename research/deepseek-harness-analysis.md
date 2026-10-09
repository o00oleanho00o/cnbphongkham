# Phân tích DeepSeek Harness (`dsh`) — cách DeepSeek làm agent harness

Ngày: 2026-10-09 · Nguồn: bản clone `E:\Desktop\clone-git\deepseek-harness` (commit `5badb15009`, tag `dsh-v0.2.1-alpha.1`, remote `github.com/deepseek-ai/deepseek-harness`) · Mục đích: rút kinh nghiệm cho agent-v2 (`pema-agent/backend`, nhánh `feat/agent-v2`).

## Phạm vi đã đọc

- **Quy mô repo:** 5.587 file code được git theo dõi; 2.384 file nguồn không phải test nằm trong `packages/`.
- **Đã đọc kỹ:** khoảng 260 file nguồn và khoảng 40 tài liệu, trải trên khoảng 120 package thuộc phần harness. Gồm: vòng lặp, tool, LLM, phiên, nén context, context, skill, subagent, workflow, lịch hẹn, webhook, hook, MCP, shell/sandbox, test, boot.
- **Tự kiểm lại từng dòng:** cách gọi API DeepSeek (`packages/llm/llm-deepseek/src/serialize.ts`, `config.ts`, `defaults.ts`) và các giá trị mặc định quan trọng (`compaction-basic/src/config.ts`, `agent-loop/src/constants.ts`, `repeat-tool-reminder/src/index.ts`).
- **Chưa đọc chi tiết:**
  - giao diện người dùng: khoảng 1.000 file trong `packages/client/*` và `apps/web`, `apps/desktop`;
  - `packages/experimental/inspector` và `webworker-runtime` (khoảng 250 file);
  - `scripts/` (287 file), các file test và `vendor/` (Cordis).
- **Về con số "200k sao":** bản clone không chứa số sao nên chưa kiểm chứng được. Repo tự ghi là bản developer preview, sẽ có thay đổi phá tương thích, và chưa được kiểm toán bảo mật (`SAFETY.md`).

## 1. Kiến trúc tổng thể: "mọi thứ là plugin"

- Toàn bộ chạy trên framework **Cordis**. Vòng lặp agent, adapter model, kho tool, log phiên… đều là plugin.
- Không có lõi "đặc quyền": muốn thay đổi thì gắn thêm plugin, không sửa lõi.
- Mỗi lần đăng ký là một "effect" trả về hàm gỡ, nên khi plugin bị gỡ thì mọi thứ nó đã đăng ký tự gỡ theo.
- **Profile** (`web`, `headless`, `sdk`, `sdk-minimal`, `acp`) gồm các **bundle** xếp lớp, cộng với các file patch YAML (`cordis.patch.yml`, `--patch`). Mỗi dòng cấu hình đều thay được bằng patch; `dsh --profile web --dump-config` in ra cây plugin thực tế.
- Quy tắc cứng: **"model nhìn thấy gì thì phải có trong log"**. Mọi thứ đi vào request đều phải dựng lại được từ log phiên; thêm một đầu vào mới cho model nghĩa là phải thêm một loại sự kiện phiên.
- Mỗi khả năng gồm 3 vai: **định nghĩa dịch vụ / bên cung cấp / bên dùng** (ví dụ `ctx.fs`, `ctx.shell`, `ctx.subagents`). Đổi bên cung cấp (ví dụ sang sandbox từ xa) thì mọi tool dùng nó đổi theo.

## 2. Vòng lặp (`packages/core/agent-loop`)

- **Turn và step:**
  - Một turn gồm 0 hoặc nhiều step; một step là một request tới model cộng các tool nó gọi.
  - **Không có giới hạn số step cứng.** Turn dừng khi không còn việc, khi bị chặn, hoặc khi bị huỷ. Lý do kết thúc lưu trong `turn/end`: completed / max-tokens / aborted / error / blocked / interrupted.
- **Hàng đợi đầu vào (inbox):**
  - Có 2 hàng đợi lưu bền: `next-turn` và `next-step` (sự kiện `agent/inbox/spliced`).
  - `steer()` chen tin nhắn vào bước kế tiếp và đánh thức vòng lặp; `inject()` chỉ thêm, không đánh thức.
- **Điểm can thiệp dạng chuỗi (waterfall):** `agent/pre-step`, `agent/request`, `llm/stream`, `tools/pre-execute`, `tools/execute`, `tools/post-execute`. Mỗi listener phải gọi `next()` để chuyển tiếp, không gọi là cắt ngang chuỗi. `agent/turn-stopping` chạy tuần tự, không có `next()`.
  - `agent/pre-step` có thể từ chối hoặc viết lại đầu vào; bị từ chối thì đóng turn mà không tốn step.
  - Nếu huỷ trong lúc chạy `agent/pre-step` hoặc `prepareCall`, không ghi system prompt cũng không ghi tin nhắn user.
- **System prompt là một node trong lịch sử** (`system/message`):
  - Prompt không đổi thì không ghi lại.
  - Nếu đổi giữa phiên mà model hỗ trợ, phần thay đổi được **gắn sau lịch sử đã cache** thay vì sửa đầu prompt, nên cache tiền tố vẫn còn. Model không hỗ trợ thì gộp lại ở đầu và bắt đầu một "request series" mới.
- **Request header gọn:** `request/header` (cấu hình + danh sách tool) chỉ ghi khi bắt đầu series hoặc khi có thay đổi; `request/context` (provider, model, cửa sổ context) chỉ ghi khi đổi.
- **Ghi cả lần gọi thất bại:**
  - `assistant/message` là kết quả thành công, có kèm luồng stream gọn đã sinh ra nó.
  - `assistant/attempt` ghi lần gọi bị lỗi, bị thử lại hoặc bị huỷ, nhưng không đưa vào lịch sử gửi model.
  - Luồng trực tiếp cho giao diện (`agent/assistant-stream`) chỉ tồn tại trong tiến trình, không lưu.
- **Vá kết quả tool khi step hỏng:** nếu step lỗi sau khi tool đã chạy, vòng lặp tự ghi kết quả cho những tool chưa có kết quả (`TOOL_OUTCOME_UNKNOWN`, `TOOL_ABORTED_BEFORE_DISPATCH`). Nhờ vậy lịch sử luôn hợp lệ để gửi lại.
- **Mỗi phiên chỉ một tiến trình ghi.** Huỷ lượt (`agent.cancel`) thì log ghi `turn/end {aborted}`; chỉ giữ `{kind, reason}` của nguyên nhân, bỏ stack trace.
- **Dọn dẹp:** `dispose()` dừng vòng lặp, chờ nó thoát hẳn rồi mới gỡ; lỗi trong listener bị chặn lại để không làm hỏng listener khác (`docs/defensive-patterns.md`).

## 3. Tool (`packages/core/tools`, `packages/guard`)

- **Định nghĩa tool:** schema cho model + schema đầu ra + hàm `execute()`, tuỳ chọn `timeoutMs`, `isConcurrencySafe(args)`, hàm trình bày cho giao diện. Model chỉ nhận name / description / parameters.
- **Phạm vi:** tool đăng ký theo lớp (toàn cục → tổ tiên → agent hiện tại), có bộ lọc allow/deny giao nhau theo chuỗi.
- **Chạy song song:** mỗi tool tự khai `isConcurrencySafe(args)` cho từng lời gọi.
  - Lời gọi an toàn đi vào nhóm song song, tối đa **10** (`DEFAULT_MAX_PARALLEL_TOOL_CALLS`).
  - Lời gọi còn lại chạy riêng, như một rào chắn.
  - Kết quả luôn trả về theo thứ tự model gọi.
- **Duyệt quyền:** `tools/pre-execute` có thể cho phép, từ chối (kèm lý do) hoặc hỏi người dùng; không có dịch vụ duyệt thì "hỏi" thành "từ chối".
- **Bộ bảo vệ dạng monotonic:** chạy sau chuỗi `pre-execute`, chỉ được chặn hoặc bỏ qua, không lật lại quyết định chặn của bước trước.
- **Timeout policy:** bọc quanh `tools/execute`; khi hết giờ thì thay kết quả bằng lỗi `TOOL_TIMEOUT`.
- **Nhắc khi lặp tool** (`repeat-tool-reminder`):
  - So sánh tham số sau khi chuẩn hoá (sắp xếp key rồi stringify).
  - Gọi y hệt lần thứ **3 / 5 / 8** thì chèn lời nhắc, mỗi mốc nhắc mạnh hơn. Chỉ nhắc, không chặn.
- **Kết quả tool quá lớn (spill):**
  - Kết quả vượt ngưỡng token được ghi ra file (quyền chỉ chủ sở hữu, 0600).
  - Model chỉ thấy **phần đầu và phần cuối** (mỗi phần nửa ngân sách) cùng đường dẫn tới file để đọc tiếp. Ghi file lỗi thì giữ nguyên kết quả.
- **Lỗi tool** (tham số sai, đầu ra sai, thực thi lỗi, bị từ chối) đều trả về như một kết quả bình thường có `isError`.

## 4. Gọi DeepSeek (`packages/llm/llm-deepseek`) — đã kiểm lại trực tiếp trong code

- **Họ không dùng API kiểu OpenAI** mà dùng **endpoint tương thích Anthropic**: `PUBLIC_BASE_URL = 'https://api.deepseek.com/anthropic'`, gọi `/v1/messages`.
- **Thinking và effort:**
  - `thinking: {type: 'enabled' | 'disabled'}` kèm `output_config: {effort: 'low' | 'high' | 'max'}`.
  - Mặc định là `high`. Khi sinh tiêu đề phiên (`purpose: 'session-title'`) thì ép tắt (`off`). Cấu hình triển khai có thể khoá `thinking: disabled`.
- **Gửi lại thinking:** gửi lại **toàn bộ** các block thinking cũ kèm `signature`, không chỉ của lượt hiện tại. Tham số tool trong lịch sử hỏng JSON thì gửi `{}`.
- **Mở rộng riêng của DeepSeek:**
  - Có thể đặt `role: "system"` **giữa hội thoại** (model khai `systemPromptUpdate: 'in-history'`) để cập nhật prompt mà không làm mất cache.
  - `tool_addition` / `tool_removal` để thêm hoặc bớt tool giữa chừng.
  - `defer_loading` cho tool.
- **Không có `cache_control`:** DeepSeek tự cache tiền tố; harness chỉ cố giữ tiền tố không đổi.
- **Kiểm tra cặp tool trước khi gửi:** mỗi `tool_use` phải có `tool_result` ngay sau, không trùng id; sai thì báo `INVALID_REQUEST` thay vì để API trả 400.
- **Watchdog luồng trả về:** stream im lặng quá **300 giây** thì huỷ (`DEFAULT_STREAM_IDLE_TIMEOUT_MS`).
- **Model mặc định:** `deepseek-flash` (có ảnh) và `deepseek-v4-pro`, context **1M token** (`DEFAULT_CONTEXT_WINDOW`), `max_tokens` 256k.
- **Ảnh:** ưu tiên Files API (dùng lại `file_id`, hết hạn 7 ngày), lỗi thì gửi inline base64; quá ngân sách thì "offload" ảnh cũ nhất và ghi sự kiện trước khi thử lại.
- **Mã lỗi ổn định:** `AUTH`, `RATE_LIMIT`, `CONTEXT_WINDOW_EXCEEDED`, `QUOTA`, `EMPTY_RESPONSE`, `SERVER`, `INVALID_REQUEST`…
- **Thử lại khi lỗi** (`packages/llm/llm-retry`):
  - Chỉ áp dụng cho các lỗi `EMPTY_RESPONSE`, `RATE_LIMIT`, `SERVER`, `TIMEOUT`, `TRANSPORT`.
  - Chờ tăng dần từ 500ms tới tối đa 10s, có jitter ±10%, tối đa 5 lần.
  - Có tôn trọng `Retry-After`.
  - Mỗi lần thử lại đều được ghi vào log (`llm/retry`, `llm/retry-started`).
- **Đo token** (`token-meter`): dựa vào usage của provider, không có tokenizer cục bộ; ước lượng heuristic khi chưa có usage.
- **Provider khác:** `llm-pi-ai` bọc thư viện `pi-ai` để dùng OpenAI, Anthropic, gateway OpenAI-compatible tự khai.
- **Khoá API:** lưu dạng bản ghi `api-key` (giá trị hoặc tên biến môi trường); tài khoản DeepSeek đăng nhập OAuth, có khoá chống làm mới token song song giữa các tiến trình.

## 5. Context và nén context (`packages/compaction`, `packages/context`, `packages/skill`)

- **Ngưỡng nén:** **80%** cửa sổ context, giữ lại khoảng **16%** phần gần nhất, chừa 65.536 token dư. Nén cả khi model báo tràn context (`context-overflow`), thử lại tối đa 1 lần.
- **Bản tóm tắt** có các mục: Primary Request and Intent, Key Technical Concepts, Files and Code, Errors and Fixes, Pending Jobs, Current Work, Next Step, Critical Context. Bọc trong `<compacted-summary>`; tóm tắt cũ được gộp vào tóm tắt mới chứ không chép nguyên.
- **Không tách cặp tool:** kiểm tra cân bằng `tool_use`/`tool_result` trước khi chọn điểm cắt.
- **Trước khi nén:** cắt bớt kết quả tool quá lớn, giữ đầu và cuối, chèn dấu `[...text omitted...]`.
- **Lưu tóm tắt:** sự kiện `compaction/start`, `compaction/summary`, `compaction/end`; bản tóm tắt thay một đoạn lịch sử bằng một tin nhắn user.
- **`/compact` thủ công** chạy như việc bảo trì giữa các turn, báo rõ lý do nếu không nén được (bận, lịch sử vừa đổi, tóm tắt hỏng…).
- **Context động** (giờ, AGENTS.md, danh mục skill, tham chiếu phiên khác) được đưa vào dưới dạng **tin nhắn user có ghi trong log**, không đưa vào system prompt.
  - Lý do: system prompt đứng yên nên cache tiền tố không bị vỡ.
  - Thông tin giờ chỉ được chèn lại sau mỗi 600 giây, kèm thời gian đã trôi qua.
- **Skill:** tìm trong các thư mục `.dsh/skills`, `.agents/skills` (dự án → home → kèm sẵn); danh mục (tên + mô tả) vào phiên như một tin nhắn user, nội dung đầy đủ tải qua tool `skill`. **Skill chỉ đọc**, agent không tự viết được.
- **Không có memory giữa các phiên.** Todo, plan mode, goal đều chỉ trong một phiên (lưu bằng sự kiện nên sống qua resume/fork). Plan mode chỉ là hướng dẫn trong prompt, không khoá tool.

## 6. Lưu phiên (`packages/session/*`)

- **Log sự kiện chỉ ghi thêm**, gồm `turn/*`, `step/*`, `user|system|assistant/message`, `assistant/attempt`, `tool/call`, `tool/result`, `request/header`, `request/context`, `compaction/*`, `session/end-seed` (fork)… Mỗi sự kiện có `seq` liên tục, `time`, và cờ `ignorable` cho loại sự kiện mà bản cũ được phép bỏ qua.
- Lịch sử gửi model được **suy ra** từ log (`deriveMessages()`), không lưu riêng.
- **Định dạng lưu trữ:**
  - File JSONL nén zstd (`session.v4.jsonl.zstd`).
  - Mỗi phiên có một lease (khoá, cả trong tiến trình lẫn giữa các tiến trình) bảo đảm chỉ một tiến trình được ghi; tiến trình đọc thì không cần khoá.
  - `append()` là ghi nỗ lực, `flush()` mới là mốc bền vững; ghi theo lô trong một khung thời gian.
  - Đuôi file bị hỏng do sập giữa chừng thì được vá; turn đang dở được đóng bằng `turn/end {interrupted}` khi mở lại.
  - Đổi định dạng thì chuyển dần v0→v1→…→v4 (mỗi bước một package), không bao giờ ghi đè dữ liệu cũ.
- **Thống kê và telemetry:**
  - `session-stats`: số turn/step, thời gian LLM và tool, độ trễ token đầu tiên, token (gồm cache).
  - Telemetry OTel mặc định **chỉ gửi đi khi người dùng gửi feedback**; có điểm can thiệp để che dữ liệu trước khi gửi, log gốc không bị sửa.
  - Tiêu đề phiên: lấy từ tin nhắn đầu, có thể sinh bằng LLM, người dùng đổi tên thì giữ cố định.
- **Tìm kiếm phiên:** chỉ mục SQLite FTS5 (`session-query-sqlite`).

## 7. Các phần mở rộng

- **Subagent** có 6 loại provider: spawn (con mới), fork (mang theo lịch sử cha), ACP, Claude Code, Codex, dsh-sdk. Có giới hạn độ sâu và tối đa 8 subagent đang chạy cùng lúc.
- **Workflow:** chạy script JS trong sandbox (PTC), gọi được nhiều agent con (`agent()`, `parallel()`, `pipeline()`); trần 1.000 agent mỗi lần chạy. Có thêm vòng lặp "Ralph" (mỗi vòng một agent con, chuyển giao JSON giới hạn kích thước).
- **Lịch hẹn:** hỗ trợ after / at / every / daily / weekly / cron (Vixie 5 trường); lịch lặp chỉ giao lần bị lỡ gần nhất.
- **Background job:** id dạng `<kind>-N`, bộ đệm đầu ra vòng có giới hạn, tool `job_*` để đọc hoặc dừng.
- **Webhook:** chỉ có GitHub, có HMAC, nhưng **không chống trùng**: một sự kiện gửi lại thì tạo thêm một phiên mới. Không có hàng đợi hay retry.
- **Hook:** tương thích với Claude Code và Codex (SessionStart, trước/sau tool, Stop, subagent start/stop), chạy lệnh qua `ctx.shell`, quyết định allow / deny / ask.
- **MCP:** stdio hoặc HTTP; tên tool dạng `mcp__server__tool` (trùng thì thêm hậu tố SHA-256); tự kết nối lại khi rớt, chờ tăng dần 500ms → 30s, tối đa 10 lần mỗi lần mất kết nối.
- **SDK / ACP:** JSON-RPC 2.0 qua dòng mới (`initialize`, `session.prompt`, `session.run`, `session.cancel`, thông báo `session.event`); SDK Python khởi động `dsh --profile sdk`.
- **Agent team (thử nghiệm):** danh sách thành viên, bảng việc có phụ thuộc, hộp thư giữa các agent.
- **Plugin manager / HMR:** cài plugin bằng pnpm; theo dõi file để nạp lại plugin khi sửa.

## 8. Thực thi và an toàn (`packages/shell`, `subprocess`, `sandbox`, `web`)

- **Biến môi trường của tiến trình con được lọc:** bỏ các tên dạng `*KEY`, `*PASSWORD`, `*SECRET`, `*TOKEN` và mọi `DSH_*`.
- **Sandbox theo từng lời gọi:** read-only / workspace-write / danger-full-access; Linux dùng bubblewrap (dự phòng Landlock), macOS dùng sandbox-exec, Windows dùng restricted token + ACL. Bị chặn thì có thể xin người dùng duyệt để chạy lại với quyền rộng hơn.
- **Web fetch:** giới hạn 5MB thân phản hồi, 100k ký tự sau giải mã; chống SSRF (chỉ địa chỉ công khai, chặn credential trong URL, kiểm tra lại sau mỗi redirect cùng origin, chặn redirect khác origin).
- **SAFETY.md:** chưa kiểm toán bảo mật, chưa sẵn sàng production; sandbox chỉ giảm rủi ro chứ không bảo đảm cô lập; khuyên chạy với quyền tối thiểu, trong VM dùng một lần.

## 9. Test — đáng học nhất

- **Phát lại phiên đã ghi, không cần API key** (`llm-replay`, `session-snapshot`):
  - Chạy thật một lần với key để ghi phiên.
  - Sau đó CI phát lại luồng trả về của model từ file đã ghi và so sánh log đầu ra với bản kỳ vọng.
  - Có bộ chuẩn hoá (che phần thay đổi theo lần chạy) dùng chung.
- **Server LLM giả** tương thích OpenAI, giả lập được lỗi ném ra, treo, hoặc trả một phần rồi hỏng.
- **Ngưỡng coverage 100%** theo từng file. Test e2e gọi API thật tự bỏ qua khi không có key. Có benchmark hiệu năng riêng.
- Test được giả định chạy song song: một test qua khi chạy một mình nhưng hỏng khi chạy cùng lúc được coi là lỗi.

## So với agent-v2 của mình

| Chủ đề | dsh | agent-v2 hiện tại | Đề xuất |
|---|---|---|---|
| Endpoint DeepSeek | Endpoint Anthropic, effort `low/high/max`, có signature | OpenAI-compatible, `reasoning_content` của lượt hiện tại | Thử trỏ adapter Anthropic (đang dùng tạm) vào `api.deepseek.com/anthropic` khi xem lại adapter này |
| Context động | Tin nhắn user có ghi trong log | Khối `<agent-context>` gắn cuối request, **không lưu** | Hợp lệ vì giữ được cache. Cân nhắc ghi khối này vào trace để dựng lại được request (S4) |
| Phiên bị cắt ngang | Tự vá kết quả tool còn thiếu, ghi `turn/end interrupted` | Chưa có: nếu sập giữa lúc chạy tool, lần sau có thể bị 400 | **Nên làm ở S4**: khi tải phiên, phát hiện `tool_use` chưa có kết quả và thêm kết quả lỗi |
| Lần gọi thất bại | `assistant/attempt`, `llm/retry` trong log | Trace có model_call lỗi, chỉ ghi metadata | Đủ dùng; ghi thêm số lần retry khi làm retry ở S4 |
| Retry | Chờ tăng dần + jitter, 5 lần, theo `Retry-After` | Chỉ thử lại một lần khi model trả về rỗng | S4: chép đúng chính sách này |
| Watchdog luồng | 300 giây im lặng thì huỷ | Chỉ có timeout tổng | S4 |
| Lặp tool | Nhắc ở lần 3/5/8 | Chưa có | S4 (loop guard): chép đúng cơ chế |
| Tool song song | Tool tự khai cho từng lời gọi, tối đa 10 | Cờ `read_only` cố định cho cả tool, tối đa 4, mỗi bước 8 lời gọi | Có thể đổi thành hàm theo tham số; không gấp |
| Kết quả lớn | Giữ đầu + cuối, phần lớn ghi ra file | Chỉ cắt phần đầu | Đổi sang giữ đầu + cuối (thay đổi nhỏ) |
| Nén context | 80% / giữ 16% / chừa 65k token | 75% / giữ 20% | Tương đương; chỉ thêm bước cắt kết quả tool lớn trước khi tóm tắt |
| Memory / skill tự viết | Không có | Có (kiểu Hermes) | Đây là **điểm hơn** của mình cho chăm sóc khách hàng, nên giữ |
| Khoá phiên | Lease, một tiến trình ghi | Chưa có (S4) | Dùng `pg_advisory_lock` theo phiên |
| Webhook / ingress | Không chống trùng | Đã lên kế hoạch ingress bền vững, chống trùng | Giữ hướng của mình (Zalo hay gửi lại tin) |
| Plugin | Đăng ký trả về hàm gỡ | S3e chưa làm | S3e: `register()` trả về disposer |
| Test | Phát lại phiên đã ghi, không cần key | `ScriptedModel` viết tay | Làm bộ ghi/phát lại từ trace và tin nhắn trong Postgres; hợp với S4 |
| Log sự kiện | Nguồn sự thật duy nhất | Bảng message cộng trace | **Chưa cần chuyển**; chỉ bổ sung những thứ trong ô "Chưa có" ở trên |

## Kết luận

dsh mạnh nhất ở ba chỗ:

1. Mọi thứ model nhìn thấy đều có trong log, nên request nào cũng dựng lại được.
2. Giữ tiền tố prompt ổn định để ăn cache (context động đi vào tin nhắn user, cập nhật system prompt gắn sau lịch sử).
3. Lịch sử luôn hợp lệ khi lượt bị hỏng hoặc bị huỷ (vá kết quả tool còn thiếu, đóng turn dở).

Ba ý đáng đưa vào S4 nhất:

1. Vá phiên bị cắt ngang khi tải lại.
2. Retry + watchdog theo đúng tham số của họ (500ms → 10s, jitter 10%, 5 lần, `Retry-After`; im lặng 300 giây thì huỷ).
3. Nhắc khi tool bị gọi lặp ở lần 3/5/8.

Các ý này sẽ đi vào kế hoạch S3d/S4 để duyệt trước khi làm.
