# Kế hoạch: vòng ngoài theo ca (case loop), bước 1 và 2

Ghi 2026-10-22. Thiết kế gốc: `DESIGN-case-loop.md`. Chủ duyệt 2026-10-22: làm `case_done` và `case_wait_until`
trước; `case_need_human` để sau. Lời duyệt đó cũng là duyệt L7 cho hai tool mới trong profile `clinic`.
**Trạng thái (2026-10-22): bước A, B, C (mục 5), mục 3.1 (trần token) và bước D (mục 6, nhắc lịch) đã làm; bước 5 (mục 7, chăm sóc lại thành plugin) đã làm 2026-10-23.** Khác kế hoạch khi làm: `TurnNode` bỏ `sends` (một câu trả lời
khách không nhận không được vào lịch sử chat; bước chỉ phán đoán là `CodeNode` tự gọi model); hai tool chỉ có khi
một plugin đang bật khai báo ca (agent không dùng ca giữ nguyên prompt và cache); động cơ nghe tin khách ở
`ChannelHub` (mọi kênh đi qua đó), không qua `on_message` của plugin; `Proactive.send_to` giữ nguyên.

## 0. Năm điều chốt lại sau khi đọc code (khác với DESIGN)

| DESIGN nói | Code cho thấy | Chốt |
|---|---|---|
| Động cơ chạy mọi nút dưới `SessionLocks.hold(session_id)` | Tin chủ động đi qua `Dispatcher.accept`, và chính lượt đó mới giữ khóa phiên (`dispatcher.py:226`). Động cơ giữ khóa rồi chờ lượt là tự khóa mình | Động cơ **không** giữ khóa phiên. Chống trùng bằng `version` (khóa lạc quan) trên hàng ca, và `message_id` của tin chủ động là duy nhất trong `agent_ingress` |
| Cột `input_tokens`, `output_tokens` của ca | Cộng từ `agent_turn` qua `external_id` cần join; chưa ai dùng | Bỏ hai cột. Ngân sách của ca = `max_turns`, `max_proactive`, bộ đếm, hạn mức theo người mỗi ngày. Ngân sách token theo phiên và ngày là bước riêng (DESIGN mục 3, bước 1) |
| `HumanNode`, trạng thái `needs_human`, tool `case_need_human` | Chủ bảo làm sau | Không có nút, không có tool. Chỉ giữ giá trị `needs_human` trong CHECK của cột `status` để sau không cần migration |
| `register_case` + `ctx.cases` bind theo plugin | Một `kind` thuộc đúng một plugin | `ctx.cases.open(kind, ...)`: động cơ tra plugin từ `kind`, không cần bind |
| Tool điều khiển tra ca qua DB | Lượt của ca chạy trong cùng tiến trình với động cơ (dispatcher cục bộ) | Tool ghi quyết định vào bộ nhớ của động cơ theo `(channel, conversation_id)` của lượt. `shortcut:` nếu lượt bị tiến trình khác vớt (sweeper), quyết định mất và ca rơi về mặc định "chờ khách"; nâng cấp khi chạy nhiều tiến trình |

Ngữ nghĩa con trỏ (`record.node`): là **nút sẽ chạy tiếp**. Sau một nút chạy xong, con trỏ = `decision.next` nếu có,
không thì theo cạnh đầu tiên từ nút vừa chạy mà `when` đúng (cạnh quay lại tăng bộ đếm; quá trần thì `stopped`).
Con trỏ rỗng mà ca chưa kết thúc = `done("end")`. `TurnNode(sends=True)` không gọi tool điều khiển = `waiting`
cho khách, con trỏ đã dời theo cạnh. Trạng thái `open` sau `apply` = động cơ chạy tiếp ngay trong cùng lượt quét,
tối đa `max_nodes_per_pass` nút.

## 1. Bước A: tầng thuần `agentcore.cases` (một commit)

Gói mới `packages/agent-core/src/agentcore/cases/`, chỉ stdlib + pydantic, không import `agent_app` hay plugin.

### `spec.py`: hình của ca

```
CaseStatus = Literal["open", "waiting", "needs_human", "done", "stopped"];  LIVE = {open, waiting, needs_human}
WaitFor    = Literal["customer", "clock", "event"]
Trigger(kind: "clock" | "customer_message" | "event", event: str | None)
StopRules(max_turns=6, max_proactive=2, max_age=timedelta(days=14), counters: Mapping[str, int] = {})
Budget(per_person_per_day: int = 2)            # dùng chung mọi ca; cài đặt của agent có thể ghi đè
CodeNode(id, run: async (state, now) -> Decision)
TurnNode(id, instruction: (state, now) -> str, sends: bool = True)
Edge(src, dst, when: ((state) -> bool) | None = None, counter: str | None = None)
Graph(start, nodes: tuple[Node, ...], edges: tuple[Edge, ...]);  Graph.node(id)
Decision(next=None, wait_for=None, wake_at=None, done=None, stop=None, patch={})
    __post_init__: done và stop không cùng có; wait_for="clock" bắt buộc wake_at; wake_at phải có múi giờ
CaseSpec(kind, state_model: type[BaseModel], goal: (state) -> str, triggers, graph, stop, budget,
         stop_if: ((state, text) -> str | None) | None, verify: (state) -> str)
CaseRecord(id, kind, key, channel, conversation_id, user_id, session_id, goal, status, node, state: Mapping,
           wait_for, wake_at, deadline, turns, proactive_sent, end_reason, version, created_at, updated_at,
           closed_at)
validate(spec): kind khớp [a-z][a-z0-9_]{0,63}; id nút duy nhất; start và mọi src/dst tồn tại; cạnh quay lại
    (chỉ số dst <= chỉ số src trong thứ tự nodes) phải có counter và counter có trần trong stop.counters;
    max_turns >= 1, max_proactive >= 0, trần bộ đếm >= 1, max_age > 0. Ném ValueError có tên nút, cạnh.
```

### `rules.py`: luật, hàm thuần

```
new_record(spec, *, key, channel, conversation_id, user_id, session_id, state, now) -> CaseRecord
    goal = spec.goal(state); node = graph.start; status open; deadline = now + stop.max_age; version 0
blocked(spec, record, now, *, enabled=True, sent_to_person_today=0, per_person_per_day) -> str | None
    "disabled" | "closed" | "expired" | "max_turns" (nút tới là TurnNode) | "max_proactive" (TurnNode sends)
    | "<counter> over <cap>" | "person_daily_cap" (TurnNode sends)
next_node(spec, record, state) -> tuple[str | None, str | None]     # (nút kế, counter của cạnh đã đi)
apply(spec, record, decision, now) -> CaseRecord                     # theo ngữ nghĩa con trỏ ở mục 0
```

### `tools.py`: hai tool điều khiển (hình ở lõi, chỗ ghi do động cơ cắm)

```
class DecisionSink(Protocol):
    async def take(self, ctx: ToolContext, decision: Decision) -> str | None   # lỗi (không có ca) hoặc None
DoneArgs(reason: str, 1..300 ký tự)
WaitArgs(wait_for: "customer" | "clock", until: datetime | None, why: str <= 300)
make_case_tools(sink) -> tuple[ToolSpec[DoneArgs], ToolSpec[WaitArgs]]
    case_done: "The goal of the current case is reached; say how you know."
    case_wait_until: "Keep the case open and come back later: when the customer answers, or at a time."
    until phải có múi giờ và sau ctx.now (không có ctx.now thì utc_now); sai → ToolOutput(is_error)
```

### Test `packages/agent-core/tests/test_cases.py`

- `validate`: từ chối cạnh quay lại không counter; từ chối counter không có trần; từ chối start lạ; nhận đồ thị
  hợp lệ (judge → write → judge với counter `unanswered`).
- `blocked`: mỗi lý do một test (bảy test), kể cả "max_turns" chỉ chặn khi nút tới là TurnNode.
- `apply`: done; stop; wait clock (cần wake_at); wait customer; `next` tường minh; theo cạnh có `when`; cạnh
  quay lại tăng bộ đếm; quá trần → stopped; hết cạnh → done("end"); TurnNode sends không quyết định → waiting
  customer với con trỏ đã dời; patch gộp vào state trước khi xét `when`.
- tools: `case_done` gọi sink với `Decision(done=...)`; `case_wait_until` clock thiếu `until` → lỗi; `until` quá
  khứ → lỗi; sink trả lỗi → `is_error`.

Lệnh: `.venv/Scripts/python.exe -m pytest packages/agent-core/tests/test_cases.py -q -p no:cacheprovider`,
ruff và pyright trên `packages/agent-core/src/agentcore/cases`.

## 2. Bước B: động cơ `agent_app/cases/`, bảng, cài đặt, lắp vào runtime (một commit, có thể tách 2)

### B1. Migration `apps/agent/alembic/versions/0004_cases.{py,sql}`

Như DESIGN 2.3 **trừ** hai cột token; `status` CHECK giữ `needs_human`; `agent_settings` thêm
`cases_enabled boolean` (NULL = profile quyết, mặc định tắt) và `proactive_per_person_per_day integer` (NULL =
2, CHECK 1..20). `downgrade` xóa hai bảng và hai cột. GRANT cho `agent_rt_app` như 0003.

### B2. `agent_app/cases/store.py`

```
class CaseStore(Protocol):
    open(record) -> CaseRecord            # INSERT; trùng (kind, key) đang sống → trả hàng đang sống (idempotent)
    get(id) -> CaseRecord | None
    live(kind, key) -> CaseRecord | None
    waiting_for_customer(channel, conversation_id) -> list[CaseRecord]
    due(now, limit) -> list[CaseRecord]   # waiting AND wake_at <= now, cũ nhất trước
    save(record) -> bool                  # UPDATE ... WHERE id AND version = :version; version + 1; False = thua
    log(case_id, kind, node, detail) -> None   # seq = max + 1 trong cùng giao dịch; detail cắt 2000 ký tự
    sent_to_person_since(user_id, since) -> int   # JOIN agent_case, kind = 'sent'
    list(status: str | None, limit) -> list[CaseRecord];  events(case_id, limit) -> list[dict]
InMemoryCaseStore (test), PostgresCaseStore (SQL text như follow_up.py, qua `retrying`)
```

### B3. `agent_app/cases/engine.py`

```
EngineSettings(tick_s=5.0, per_pass=20, max_nodes_per_pass=10, turn_timeout_s=180.0)
class CaseEngine(DecisionSink):
    __init__(store, specs: () -> Mapping[kind, (plugin, CaseSpec)], *, tenant_id, enabled: () -> bool,
             per_person_per_day: () -> int, zone: () -> ZoneInfo, clock, settings)
    attach(proactive: Proactive, session_for: async (channel, conversation_id) -> str)   # serve gọi khi có dispatcher
    tools() -> list[ToolSpec]                      # hai tool, sink = self
    # Cases (cái plugin thấy qua ctx.cases)
    open(kind, key, *, channel, conversation_id, user_id, state) -> CaseRecord   # validate state_model; session_for
    wake(kind, key, patch=None) -> bool            # ca sống: wake_at = now, patch vào state
    get(kind, key) -> CaseRecord | None
    # trigger
    on_message(msg: ObservedMessage)               # origin inbound, không group, không PROACTIVE:
                                                   #   mọi ca waiting-for-customer của chat: stop_if → stopped;
                                                   #   spec có trigger customer_message → wake_at = now
    run()                                          # while True: pass_once(); sleep(tick_s)
    pass_once() -> int                             # due(now, per_pass) → step(record) từng ca
    step(record)                                   # tối đa max_nodes_per_pass lần:
                                                   #   blocked? → stopped + log("blocked")
                                                   #   CodeNode: await run(state, now); lỗi → log, dừng lượt quét này
                                                   #   TurnNode: message_id = f"case:{id}:{turns}"; proactive.send_to(
                                                   #     instruction = f"[Hệ thống · ca {kind}] " + goal + verify + instruction);
                                                   #     turns += 1; counted → proactive_sent += 1, log("sent");
                                                   #     quyết định = self._taken.pop((channel, conversation_id)) hoặc Decision()
                                                   #   apply → save (thua version → bỏ, log) → log("decision")
                                                   #   status open → vòng tiếp; khác → dừng
    take(ctx, decision)                            # DecisionSink: có ca đang chạy cho chat này thì ghi, không thì lỗi
```

Tin của ca mang `PROACTIVE` nên `on_message` tự bỏ qua tin của chính nó; `render_transcript` của chăm sóc lại
đã có cách nhận dấu `[Hệ thống ·`, giữ nguyên.

### B4. Hợp đồng plugin

- `host.py`: `_Loaded.cases: list[CaseSpec]`; `Contributions.cases`; `PluginContext.register_case(spec)`
  (validate; một kind một plugin trong `_check_unique`); `PluginContext.cases` → `Cases` Protocol (`open`,
  `wake`, `get`), `PluginError` khi chưa có động cơ (ngoài `agent serve`, như `proactive`); `PluginHost.use_cases(engine)`.
- `agent_app/plugins/__init__.py` xuất `Cases`.
- `assembly.build_agent(..., extra_tools: Sequence[ToolSpec] = ())`: đăng ký sau tool lõi, trước tool plugin.

### B5. Cài đặt (`agent_settings.py`, gateway)

`StoredAgentSettings.cases_enabled`, `.proactive_per_person_per_day`; `SCALAR_FIELDS` thêm hai tên; SQL đọc
ghi hai cột; `EffectiveAgent.cases: CasesConfig(enabled, per_person_per_day)`; `AgentSettingsPatch` ở gateway
nhận hai trường; test `test_agent_settings.py` thêm một ca lưu và đọc lại.

### B6. Lắp vào runtime và gateway

- `runtime.py`: với DB, tạo `CaseEngine(PostgresCaseStore, specs=lambda: {s.kind: (plugin, s) ...} từ
  `host.contributions().cases`, enabled=lambda: settings.effective.cases.enabled, ...)`; `host.use_cases(engine)`;
  `Runtime.cases`; `build(added)` truyền `extra_tools=engine.tools()`; `channel_hub(...)` dùng
  `observe=` gọi `engine.on_message` rồi `plugins.observe`.
- `gateway.create_app(..., cases=engine)`: `engine.attach(DispatcherOutbox(dispatcher), dispatcher.session_for)`
  (cùng chỗ `use_proactive` hôm nay), thêm task nền `engine.run()`; route admin `GET /v1/admin/cases?status=`,
  `GET /v1/admin/cases/{id}` (hàng + nhật ký). Chưa có `resume`, `close` (đi cùng `case_need_human`).

### B7. Test

- `apps/agent/tests/test_cases_engine.py` (store RAM, `ScriptedModel`, `FakeProactive` như `test_follow_up_send.py`):
  một ca clock chạy CodeNode rồi TurnNode và chờ khách; khách nhắn → `stop_if` dừng ca trước khi chạy nút;
  khách nhắn thường → wake và chạy nút kế; `case_done` trong lượt → done; `case_wait_until` clock → waiting đúng
  `wake_at`; hai lần chạy cùng `turns` gửi một lần (`message_id` trùng); `cases_enabled=false` → blocked; hạn mức
  theo người cộng hai ca khác kind; thua `version` thì không ghi.
- `apps/agent/tests/test_cases_db.py` (đánh dấu `db`, chạy trên `scratch_pema`): open idempotent theo unique
  index; due; save thua version; sent_to_person_since.
- `test_tool_allowlist.py`: `APPROVED_TOOLS` thêm `case_done`, `case_wait_until` → `"agentcore"`, ghi "chủ duyệt
  2026-10-22, DESIGN-case-loop.md"; `test_every_tool_in_the_code_is_on_the_approved_list` đỏ nếu quên.
- Test cấu trúc import (T9 mới, cùng file): `agentcore/**` không import `agent_app`, `plugins`;
  `agent_app/**` (trừ tests) không import `plugins.`.
- `test_plugins.py`: `register_case` hai plugin cùng kind → `PluginError`; `ctx.cases` ngoài serve → `PluginError`.

Lệnh: pytest các file trên + `test_agent_settings.py`, `test_gateway.py`, `test_plugins.py`; `ruff` và `pyright`
trên `apps/agent/agent_app/cases`, `host.py`, `assembly.py`, `runtime.py`, `gateway.py`, `agent_settings.py`.
Test DB cần container `pema-scratch-pg` và `PEMA_TEST_DATABASE_URL`, không bao giờ DB demo.

### B8. Sau khi xanh

- Luật `diagram-after-task`: ERD `agent_rt` (thêm `agent_case`, `agent_case_event`, hai cột settings) và một
  sơ đồ workflow "một ca chạy thế nào" trong `.archify/`, cập nhật `index.html` mục 2d.
- `HANDOFF-agent-v2.md`: mục mới "Ca (case loop)": đã có gì, chưa có gì (`case_need_human`, resume/close, chăm
  sóc lại chưa chuyển), rủi ro shortcut nhiều tiến trình.
- `.claude/rules/agent-crm-boundary.md` T9: hai tool lõi mới trong danh sách (không ra mạng, chỉ ghi `agent_rt`).

## 3. Chưa làm trong hai bước này, làm sau theo thứ tự

1. ~~Ngân sách token theo phiên và ngày trước `run_turn`~~ **đã làm 2026-10-22:** `TokenBudget` (`dispatcher.py`) kiểm trước mỗi lượt
   tổng token (prompt, kể cả phần cache, và sinh ra) của các lượt trong ngày theo giờ địa phương, đếm từ
   `agent_turn`: một phiên (`tokens_per_session_per_day`, mặc định 2 triệu) và cả agent (`tokens_per_day`,
   mặc định 50 triệu), hai cột của `agent_settings` (migration `0006_token_budget`, có index `agent_turn(tenant_id,
   agent, started_at)`). Quá trần thì lượt không chạy, tin hỏng với `token_budget`: khách nhận câu báo lỗi có sẵn,
   tin chủ động bị bỏ qua, lượt của ca tính là đã dùng. Lượt vượt trần vẫn chạy hết (kiểm trước lượt, không giữa lượt).
2. ~~Hợp đồng `JudgeService`, `EmbeddingService` ra package trung lập~~ **đã làm 2026-10-22:** thư mục trung lập
   `apps/agent/plugin_kit/` (không phải package mới: image đã chép cả `apps/agent`, nên Dockerfile, compose, `uv.lock`
   không đổi) giữ hợp đồng dịch vụ và `KeySet` (trước ở `plugins/sso/keys.py`, `crm` import thẳng). Harness hết mang
   hợp đồng riêng, CLI hết gọi tên plugin `web`; T9 thêm test plugin không import plugin khác.
3. ~~Chăm sóc lại thành plugin `follow_up` trên động cơ~~ **đã làm 2026-10-23, mục 7** (DESIGN 2.5). Lý do hoãn lúc đầu: route
  `/v1/admin/follow-ups` và hai trường `follow_up_*` của settings đang được frontend dùng, mà frontend do phiên
  Claude khác giữ; đổi cùng lúc với phiên đó.
4. ~~Nhắc lịch của `crm` lên động cơ (DESIGN 2.6)~~ **đã làm 2026-10-22, mục 6.** Khác kế hoạch khi làm: `check`
   kết thúc ngay ca của lịch đã hủy hay dời, trước khi xét mốc (ca được sự kiện đánh thức không đợi tới mốc mới dừng).
5. `case_need_human`, `HumanNode`, route `resume`/`close`, giao diện nhân viên.
6. ~~Ngưỡng `run_turn` và nén ra cài đặt~~ **đã làm 2026-10-23, mục 8.**

## 4. Rủi ro ghi trước

- Động cơ không có ca nào chạy cho tới khi một plugin `register_case`: sau bước B, hệ chạy y như cũ. (Đã khác khi
  làm: hai tool chỉ có khi một plugin đang bật khai báo ca, nên prompt và cache không đổi; quyết định của tool nằm
  ở `agent_case.pending` từ bước C2, không còn trong RAM.)
- `apply` chạy tiếp nút `open` ngay trong một lượt quét: trần `max_nodes_per_pass` và `max_turns` giữ cho không
  quay vô hạn; test có ca cho cả hai.

## 5. Bước C: sửa hai lỗ sau bước B (ghi 2026-10-22; C1 và C2 đã làm cùng ngày)

### C1. Tin chủ động không bao giờ gộp lượt với tin khác (một commit, làm trước)

**Lỗi:** `Dispatcher._gather` gom các tin xếp hàng của cùng `user_id` vào một lượt, và `steer_in` nhét tin đến giữa
lượt vào lượt đang chạy. Tin chủ động (ca, chăm sóc lại, nhắc lịch của `crm`) mang `user_id` của khách nên bị gom
chung. Chỉ câu trả lời của tin đứng đầu được gửi đi: tin chủ động đứng đầu mà model trả `SKIP` thì câu hỏi thật của
khách mất trả lời; tin khách đứng đầu thì chỉ dẫn của vòng lẫn vào câu khách hỏi. Lỗi có thật hôm nay với nhắc lịch.

**Sửa:** trong `_gather`, lead là tin chủ động thì không gom gì; gặp một tin chủ động khi đang gom tin khách thì dừng.
`steer_in` dùng chính `_gather` nên được sửa theo. Tin chủ động bỏ qua `_quiet` (không ai đang gõ tin đó).

**Test** (`test_queue_modes.py`): tin khách rồi tin chủ động xếp hàng thành hai lượt, hai câu trả lời; tin chủ động
rồi tin khách cũng hai lượt, `SKIP` của lượt chủ động không nuốt câu trả lời của khách; chế độ `steer` không nhét tin
chủ động vào lượt của khách và ngược lại.

### C2. Quyết định của tool điều khiển xuống DB, gắn với đúng tin của lượt (một commit)

**Lỗi:** quyết định nằm trong dict của tiến trình, tra theo chat. Mất khi agent khởi động lại giữa lượt (sweeper chạy
lại lượt nhưng dict trống) hoặc khi tiến trình khác chạy lượt; và một lượt bình thường của khách chạy trong lúc tin
của ca còn xếp hàng có thể gọi `case_done` mà vẫn được gán cho ca.

**Sửa:**
- Lõi: `ToolContext.message_id` (mã tin mà lượt trả lời, chung cho mọi tool), `run_turn(message_id=...)`; dispatcher
  truyền `lead.external_id`. Nhờ C1, lead của lượt chủ động luôn là chính tin chủ động.
- `agentcore.cases`: `turn_message_id(case_id, turn)` và `parse_turn_message_id(text)` (chuyển tiền tố `case:` từ
  động cơ về lõi); `Decision` đọc ghi JSON qua `TypeAdapter`.
- Migration `0005_case_pending`: `agent_case.pending jsonb` (quyết định của lượt đang chạy, kèm số lượt).
- Tool: không có `case:<id>:<lượt>` trong `ctx.message_id` thì từ chối (lượt của khách không điều khiển được ca); có
  thì `store.set_pending(id, turn, decision)`: `UPDATE ... SET pending WHERE id AND turns = :turn AND status sống`,
  không tăng `version` (động cơ đang giữ bản đọc trước lượt). Ca đã đi tiếp thì từ chối.
- Động cơ: bỏ `_running`, `_taken`; sau lượt đọc `store.pending(id, turn)`; `save` ghi `pending = NULL`.
- Phục hồi khi agent chết giữa lượt: ca vẫn `open` với `turns = n`; lần quét sau gửi lại cùng mã `case:<id>:<n>`,
  hàng đợi trả bản ghi cũ (không chạy hay gửi lần hai), động cơ chờ nó xong rồi đọc `pending` từ DB.

**Test:** lượt của khách gọi `case_done` bị từ chối; quyết định của lượt ca sống qua một động cơ mới (giả lập khởi
động lại) cùng store; gửi lại cùng mã lượt chỉ tính một tin; ca đã đi tiếp thì `set_pending` từ chối; test DB cho
`pending` và chuyện không tăng `version`; `test_run_turn` kiểm `message_id` tới `ToolContext`.

**Vẽ lại sau khi xanh:** cột `pending` trong ERD `agent_rt` và hình "Agent · ca" của `pema-system-design.html`.


## 6. Bước D: nhắc lịch của `crm` chạy trên động cơ ca (DESIGN 2.6; ghi 2026-10-22, đã làm cùng ngày)

Chủ chọn làm 2.6 trước 2.5 (chăm sóc lại), vì 2.5 đụng route và cài đặt mà frontend đang dùng. Nhắc lịch thành ca
thật đầu tiên chạy hết vòng: plugin khai báo ca, động cơ đợi đồng hồ, kiểm lại, gửi, ghi nhật ký.

### 6.1 Đọc code thấy gì (khác với DESIGN 2.6)

- **Một ca cho mỗi mốc, không phải một ca cho mỗi lịch.** DESIGN viết một ca giữ cả hai mốc (24h, 3h). Nhưng theo
  `apply`, sau một `TurnNode` ca chờ khách, không có giờ dự phòng; mốc 3h sẽ không bao giờ tới nếu khách không nhắn
  lại. Một ca một mốc thì gửi xong là hết đồ thị, ca `done`, không cần sửa lõi. Khóa ca:
  `f"{appointment_id}:{int(starts_at.timestamp())}:{mark}"`, nên lịch dời giờ là khóa mới.
- **`claim_mark` ở lại, làm chốt "mỗi mốc một lần".** Chỗ chống trùng của động cơ chỉ áp cho ca còn sống; ca đã
  `done` mà vòng quét mở lại cùng khóa thì sẽ thành ca mới và gửi lần hai. Bảng `crm_reminder_sent` đã có khóa
  duy nhất đúng nghĩa đó, và còn giữ các mốc đã gửi trước khi chuyển, nên lúc chuyển không ai bị nhắc hai lần.
  Không cần migration.
- **Trần mỗi người mỗi ngày phải do một chỗ quyết.** Nếu `decide` đếm riêng (`crm_reminder_sent`) mà động cơ chặn
  ở nút gửi theo trần chung, con trỏ sẽ nằm ở `send` tới hôm sau, và sáng hôm sau gửi luôn, không kiểm lại (có thể
  lúc 00:00, có thể lịch đã hủy). Nên `decide` hỏi động cơ còn được gửi bao nhiêu tin cho người này hôm nay
  (cùng luật động cơ dùng ở `blocked`), và bỏ mốc khi hết chỗ, như hôm nay.

### 6.2 Hình của ca `reminder`

- **State** (`ReminderCase`): `appointment_id`, `starts_at`, `mark` (`24h`, `3h`), `status` (lấy lại lúc kiểm),
  hai bộ đếm `looks` và `retries`.
- **Đồ thị:** `check` (`CodeNode`) → `send` (`TurnNode`). Cạnh quay `check → check` mang bộ đếm `looks`, trần 10.
  **Cạnh lỗi** `send → check` (`on="error"`) mang bộ đếm `retries`, trần 3 (chủ chọn 2026-10-22). Mọi lần gửi,
  kể cả lần thử lại sau lỗi, đều đi qua `check` ngay trước đó.
- **`check`:** đọc lại lịch và người từ `crm_reminder`, `crm_person`, chạy `decide()` như hôm nay (bảy lý do bỏ giữ
  nguyên):
  - chưa tới mốc → `next="check"`, chờ đồng hồ tới `due_at`;
  - giờ yên lặng → chờ tới hết giờ yên lặng;
  - bỏ → `stop=f"skip:{reason}"`;
  - gửi → `patch={"status": ...}`, `next="send"`.

  Lịch đã dời giờ (`starts_at` khác state) → `stop="skip:moved"`.
- **`send`:** lời dặn của `instruction_for` (giờ, ngày do code viết, có lối `SKIP`). Gửi xong thì hết cạnh, ca
  `done`.
- **Trigger:** `clock` và `event` (`appointment_changed`). **Stop:** `max_turns=1`, `max_proactive=1`, `max_age=2 ngày`. **Budget:**
  `per_person_per_day = policy.per_day`. **Goal:** "khách biết lịch lúc HH:MM ngày …, mốc …". **Verify:** lịch còn
  `booked`/`confirmed` trong `crm_reminder`, tin nhắc nằm trong chat.

### 6.3 Ai mở ca

- `Reminders.pass_once` hết gửi, chỉ còn mở ca. Với mỗi lịch trong cửa sổ hiện có (`upcoming`, tới mốc dài nhất +
  1 giờ) có người đồng ý và có chat 1-1, với mỗi mốc chưa có trong `crm_reminder_sent`:
  `claim_mark(visit, mark, "case")` rồi `ctx.cases.open("reminder", key, ...)`. Ca tự đợi tới mốc.
- Job `reminders` vẫn chạy mỗi giờ, khi có sự kiện CRM (`wake`), và đối soát 24 giờ như cũ.
- Thứ tự giữ như code hôm nay: claim trước, mở ca sau. Lỗi giữa hai bước thì mất mốc đó chứ không bao giờ nhắc
  hai lần. Ngoài `agent serve` (chưa có đường gửi, `ctx.proactive` báo `PluginError`) thì bỏ cả lượt quét và
  không claim gì, như hôm nay.
- **Sự kiện đánh thức ca đang đợi (chủ chọn cách B, 2026-10-22).** Route `/v1/hooks/crm/events` đọc lịch cũ
  trước khi ghi sự kiện. Ghi xong, với mỗi mốc của lịch cũ, nó gọi `ctx.cases.wake("reminder", key)`. Ca thức
  dậy và chạy `check` ngay: lịch hủy thì dừng với `skip:over`, dời giờ thì dừng với `skip:moved`. Nhật ký ghi
  đúng lúc có sự kiện, không phải lúc tới mốc. Ca cho giờ mới do vòng quét mở như cũ, vì `on_change` vẫn đánh
  thức vòng quét. Không cần điều kiện "chỉ đánh thức ca ở `check`": nhờ cạnh lỗi, con trỏ không bao giờ nằm
  chờ ở `send`.

### 6.4 Đổi ở lõi và động cơ (nhỏ, chung cho mọi ca)

- **Cạnh lỗi.** `Edge` thêm `on: Literal["ok", "error"] = "ok"` (`agentcore.cases`, tầng hình, thuần). Cạnh
  thường đọc như cũ; cạnh `error` chỉ đi khi nút ở đầu cạnh lỗi. Luật sẵn có vẫn áp: cạnh quay lui phải có bộ
  đếm có trần. Động cơ (`_retry_later`): nút lỗi mà có cạnh `error` thì dời con trỏ theo cạnh đó, cộng bộ đếm
  (chạm trần thì dừng ca), rồi chờ 5 phút. Không có cạnh lỗi thì giữ như cũ (thử lại ở chính nút đó). Động
  cơ không biết ca của ai; plugin chỉ khai báo cạnh, không chạm con trỏ.
- `CaseEngine.room_today(plugin, kind, channel, user_id) -> int`: số tin mọi ca còn được gửi người này hôm nay, bằng
  `min(spec.budget, cài đặt) - đã gửi`, đúng phép tính của `blocked`.
- `ctx.cases.room_today(kind, channel, user_id)` gọi tới nó (`Cases`, `CaseService`).

### 6.5 Bỏ đi

- Phần gửi của `Reminders` (`_send`, `message_id`, `INSTRUCTION_MARK`; `turn_text` đã gắn dấu `[Case · reminder]`).
- `ReminderStore.sent_since` và chỗ dùng nó.
- Bảng `crm_reminder_sent` giữ lại: là chốt "một lần".

### 6.6 Đổi hành vi (chủ cần biết)

- **Nhắc lịch chỉ chạy khi `cases_enabled` bật.** Công tắc khẩn của mọi ca nay cũng tắt nhắc lịch; mặc định là
  tắt. Sau khi deploy, admin bật một lần (`PATCH /v1/admin/settings {"cases_enabled": true}`). Thứ tự bật trong
  `infra/README.md` thêm bước này. Nếu chưa bật, nhắc lịch ngừng.
- Trần mỗi người mỗi ngày nay tính chung cho mọi ca (hôm nay chỉ có nhắc lịch, nên như cũ). Chỉnh bằng
  `proactive_per_person_per_day`; `reminders_per_day` của plugin vẫn là trần riêng của nhắc lịch.
- Model thấy lời dặn trong khung của ca (tiếng Anh của harness và lời dặn tiếng Việt của plugin). Hai tool
  `case_done`, `case_wait_until` có trong profile `clinic` (đã duyệt L7, T9).
- Mã tin đổi từ `crm-reminder:…` sang `case:<id>:0`.
- **Gửi lỗi thì kiểm lại rồi mới thử.** `send_to` chỉ ném lỗi khi không nói được với hàng đợi (DB lỗi); hết giờ
  chờ hay kênh không gửi được thì nó trả kết quả, ca kết thúc bình thường. Khi lỗi, ca quay về `check` theo cạnh
  lỗi, 5 phút sau kiểm lại (lịch, đồng ý, giờ yên lặng, chỗ trong ngày) rồi mới gửi; lỗi tới lần thứ 3 thì ca
  dừng. Lần thử lại dùng cùng số lượt, nên cùng mã tin: tin đã vào hàng đợi thì không bao giờ gửi hai lần.
- **Lỗ còn lại** (ghi `shortcut:` trong code): tin đã vào hàng đợi rồi DB lỗi lúc chờ kết quả, rồi lịch bị hủy
  trong 5 phút sau đó. Tin trong hàng đợi vẫn được dispatcher chạy, kiểm lại không thu hồi được.

### 6.7 Test

- **Giữ:** test của `decide`, `ReminderPolicy`, `instruction_for`, đối soát.
- **Viết lại trên động cơ** (store trong RAM, kênh giả như `test_cases_engine`):
  - mốc tới thì gửi đúng một lần dù quét nhiều lần;
  - mốc chưa tới thì ca chờ đúng giờ;
  - giờ yên lặng dời tới lúc hết;
  - lịch hủy trước mốc → `skip:over`, không gửi;
  - lịch dời giờ → ca cũ `skip:moved`, ca mới theo giờ mới;
  - sự kiện hủy hay dời làm ca đang đợi dừng ngay, không đợi tới mốc;
  - gửi lỗi rồi lịch bị hủy → ca quay về `check` và dừng, không gửi;
  - gửi lỗi rồi lịch vẫn còn → lần sau gửi đúng một tin; lỗi 3 lần thì ca dừng;
  - mốc đã có trong `crm_reminder_sent` (gửi trước khi chuyển) không gửi lại;
  - hết chỗ trong ngày → `skip:daily_cap`;
  - `cases_enabled` tắt thì không gửi gì.
- **Động cơ:** `room_today` khớp với `blocked`; ca không có cạnh lỗi thử lại ở chính nút như cũ.
- **Lõi** (`test_cases.py`): cạnh `error` quay lui không có bộ đếm bị từ chối; cạnh `error` không được chọn khi
  nút chạy xong bình thường.
- **Chạy lại:** `tests/crm/`, `test_cases_engine.py`, `test_tool_allowlist.py` (T9) và các test ranh giới của `crm`.

### 6.8 Sau khi xanh

- Sửa đoạn nhắc lịch trong `infra/README.md`, HANDOFF, mục 3 của kế hoạch này.
- Không có migration, nên `pema-system-design.html` chỉ sửa chữ nếu có đoạn tả vòng nhắc lịch.
- `/archify`: sơ đồ vòng nhắc lịch, hoặc thêm nhánh `crm` vào workflow của ca.
- Ranh giới L1–L7 không đổi: không thêm tool, route, sự kiện, trường dữ liệu hay biến môi trường.

## 7. Bước 5: chăm sóc lại thành plugin `follow_up` trên động cơ ca (DESIGN 2.5; ghi 2026-10-22, chủ nói "go" cùng ngày, kèm: phán đoán bằng Jev khi có; đã làm 2026-10-23)

**Khác kế hoạch khi làm:** (1) `TurnNode` thêm `look_again` (lõi, chung cho mọi ca): sau lượt gửi, ca đợi khách
nhưng tối đa chừng đó rồi chạy nút kế dù khách im; không có nó thì tin chủ động (không mở lại ca) để ca đợi khách
mãi và `unanswered` không bao giờ lên 2. (2) `write → quiet` thay vì `check → quiet`; `judge` có cạnh lỗi về `quiet`.
(3) Ca giữ `sending_at` (lúc `check` cho gửi), `quiet` đổi nó thành `last_sent_at`. (4) `deadline` của ca chuyển từ
bảng cũ là `next_at + 74 ngày` (tạm ngưng tối đa 60 ngày + 14). (5) Đường gửi chủ động chung ở `agent_app/proactive.py`,
`Dispatcher.history` là đường đọc chat của plugin.

Xóa vi phạm cuối trong `.claude/rules/agent-harness.md` ("mọi thứ là plugin", H6): harness hết biết chăm sóc lại,
tin chăm sóc lại tính chung vào trần mỗi người mỗi ngày với nhắc lịch.

### 7.1 Đọc code thấy gì (khác với lúc hoãn và với DESIGN 2.5)

- **Frontend không dùng gì của chăm sóc lại.** Grep `frontend/src` không có `follow_up`, `follow-ups` (trang cài
  đặt chỉ vẽ các trường nó biết). Lý do hoãn ở mục 3 bước 3 không còn: bỏ được route `/v1/admin/follow-ups`, hai
  trường `follow_up_*` của settings và cờ CLI mà không đụng frontend. Danh sách ca đã có ở `/v1/admin/cases`.
- **Plugin chưa đọc được lịch sử chat.** Nút `judge` cần đoạn hội thoại (hôm nay `FollowUps` giữ `SessionStore`).
  Plugin chỉ có `ctx.model`, `ctx.proactive`, `ctx.cases`.
- **Plugin nghe được câu trả lời của agent** (`ctx.on_message`, `origin="agent"`, cả tin chủ động, có `metadata`),
  nhưng không biết người: `ObservedMessage` của câu trả lời có `sender_id=""`.
- **Không cần quét bảng hàng đợi để biết hội thoại im.** Agent chỉ trả lời (không chủ động) khi khách vừa nhắn; nên
  "câu trả lời không chủ động vừa đi" = "khách vừa nói chuyện", và "ca đã dừng chỉ mở lại khi khách nhắn trước" tự
  đúng: ca mới chỉ mở từ câu trả lời đó. Plugin không đọc `agent_ingress` (H1).
- `DispatcherOutbox.send_to` là đường gửi chủ động chung (động cơ ca, `ctx.proactive`), không thuộc chăm sóc lại.

### 7.2 Đổi ở harness và lõi (nhỏ, chung cho mọi plugin, H10)

1. `ObservedMessage.user_id: str = ""` (lõi `agentcore.channels`): người của cuộc chat (câu trả lời của agent:
   người được trả lời). `ChannelHub._tell_of_reply` điền `record.user_id`.
2. `ctx.chat_history(channel, conversation_id, limit=40) -> list[Message]`: chỉ đọc, các tin của phiên hiện tại của
   cuộc chat (qua `session_for` + `SessionStore.load`). `PluginHost.use_history(...)` gắn lúc `agent serve` như
   `use_proactive`; chưa gắn thì `PluginError`. Chỉ đọc phiên của agent, không bảng nào khác (L4 không đổi).
3. `DispatcherOutbox` chuyển sang `agent_app/proactive.py` (bỏ `send(row: FollowUp, ...)`, giữ `send_to`).

### 7.3 Plugin `apps/agent/plugins/follow_up/`

- `plugin.toml`: không migration riêng; `user_config.channels` (danh sách kênh, mặc định rỗng = không theo dõi kênh
  nào), `user_config.timezone` (mặc định `Asia/Ho_Chi_Minh`). Bật/tắt = bật/tắt plugin; ca chạy khi
  `cases_enabled` bật.
- `rules.py`: chép nguyên phần thuần của `follow_up.py` (`FollowUpPolicy`, `decide`, `may_send` thành kiểm trên
  state, `asks_to_stop`, `SYSTEM_PROMPT`, `instruction_for`, `render_transcript`, `parse_verdict`).
- **State** `FollowUpState`: `replied_at` (câu trả lời cuối của agent), `judged_at`, `state`, `reason`, `next_at`,
  `paused_until`, `last_sent_at`, `unanswered`, `restarts`, `retries`.
- **Đồ thị** (khóa ca `f"{channel}:{conversation_id}"`):

  | Nút | Loại | Làm gì |
  |---|---|---|
  | `quiet` | code | chưa im đủ `quiet_after` (2 giờ) từ `replied_at` → đợi đồng hồ; im quá `quiet_after + 1 ngày` (dịch vụ chết lâu) → done; còn lại → `judge` |
  | `judge` | code | đọc `ctx.chat_history`, lưới từ khóa `asks_to_stop` trên lượt khách cuối, phán đoán (7.3a), `decide()`: `done` → done; `hard_decline`, `negative` → stop; `hesitant`, `call_back`, `soft_decline` → ghi hẹn, sang `check` |
  | `check` | code | kiểm ngay trước gửi (H5): khách nhắn sau lần phán đoán (`replied_at > judged_at`) → về `quiet`; hẹn trễ quá `max_late` (2 ngày) → done; chưa tới hẹn, ngoài giờ 8–20, chưa đủ 24 giờ từ tin trước, đang tạm ngưng → đợi đồng hồ tới lúc được; hết chỗ hôm nay (`ctx.cases.room_today`, H6) → đợi sang ngày; còn lại → `write` |
  | `write` | lượt | `instruction_for(state)`: một tin tự nhiên hoặc `SKIP` |

  Cạnh: `quiet→judge`, `judge→check`, `check→write`, `check→quiet` (counter `restarts`, trần 20),
  `write→quiet` (counter `unanswered`, trần 2: hai tin liền không được trả lời thì ca dừng, như hôm nay),
  `write→check` cạnh lỗi (counter `retries`, trần 3).
  `StopRules(max_turns=4, max_proactive=4, max_age=14 ngày)`, `Budget(per_person_per_day=1)`,
  `stop_if = asks_to_stop` (khách nhắn "đừng nhắn nữa" khi ca đang đợi → ca dừng ngay; động cơ đã làm sẵn).
- **Ai mở, ai đánh thức** (`ctx.on_message`): câu trả lời của agent (`origin="agent"`) trong cuộc chat một-một của
  kênh trong `channels`:
  - không chủ động (khách vừa nhắn): `ctx.cases.wake(..., {"replied_at": at, "unanswered": 0})`; không có ca sống
    thì `ctx.cases.open(...)` ở `quiet`;
  - chủ động (tin của ca này hay ca khác vừa đi): chỉ `wake(..., {"replied_at": at})` để `quiet` đếm im từ đó.

  Không nghe tin khách trực tiếp: tin khách luôn kéo theo câu trả lời, và `stop_if` của động cơ đã nghe tin khách.
- Model trả `SKIP` ở `write`: ca đợi khách (luật sẵn của `TurnNode`), không nhắn nữa tới khi khách nhắn.

### 7.3a Phán đoán: Jev trước, model chat khi Jev không chắc (chủ yêu cầu 2026-10-22)

- Có dịch vụ `judge` (plugin `jev` bật, `ready()`): hỏi **một** câu `choice` tên `state`, sáu phương án đúng sáu
  trạng thái, mô tả và ví dụ lấy từ `SYSTEM_PROMPT` (luật giữ nguyên), `state` của request là giờ hiện tại và
  đoạn hội thoại `render_transcript`. Câu trả lời: `choice`, `probabilities`, `confidence` (0–1, tài liệu
  TypeSafe `primitives/choice`).
- Dùng kết quả của Jev khi `confidence >= 0.6` và trạng thái không phải `call_back`. Giờ nhắn lại lấy mặc định
  của `FollowUpPolicy` (`hesitant` 24 giờ, `soft_decline` tạm ngưng 14 ngày), vì Jev không đọc ra được ngày giờ;
  lý do ghi `Jev: <trạng thái> (<độ tin>%)`.
- Còn lại gọi model chat như hôm nay: Jev không bật, chưa sẵn sàng, lỗi, trả dữ liệu lạ, không chắc (`confidence`
  thấp, trong đó có "không chắc thì chọn done" của prompt), hoặc ra `call_back` (khách hẹn giờ cụ thể, cần
  model tính `after_h`).
- Nhật ký ca ghi ai phán đoán (`jev` hay `model`) và độ tin, để chủ đo tỉ lệ Jev đỡ được và độ đúng.
- `user_config.judge_with_jev` (mặc định bật), `user_config.jev_min_confidence` (mặc định 0.6).
- **Rủi ro:** đoạn hội thoại của khách (có thể có tên, số điện thoại, bệnh) đi tới TypeSafe (Mỹ); hôm nay Jev
  chỉ nhận câu tìm và tài liệu. Chủ đã chấp nhận dữ liệu ra nước ngoài cho Jev (PLAN-jev-plugin, 2026-10-14);
  tắt bằng `judge_with_jev = false`. Jev chưa được đo trên tiếng Việt: ngưỡng độ tin là chỗ chỉnh.

### 7.4 Bỏ đi

`agent_app/follow_up.py`; `FollowUpConfig`, `follow_up_enabled`, `follow_up_channels` ở `agent_settings.py`,
gateway (`PATCH` settings, `/v1/admin/follow-ups`, task nền `follow-ups`), `runtime.py`, `cli.py` (`--follow-up`,
`--follow-up-channel`); `agent_follow_up` khỏi `db_roles.py`.

### 7.5 Migration `0007_follow_up_plugin.{sql,py}` (`pema_agent`)

1. Hẹn còn sống (`next_at` có, chưa `stopped`) → một hàng `agent_case` (`plugin='follow_up'`, `kind='follow_up'`,
   nút `check`, `waiting` đồng hồ tới `next_at`, state từ các cột cũ, `deadline = now() + 14 ngày`). Hàng khác bỏ:
   `stopped` không cần giữ vì ca mới chỉ mở khi khách nhắn trước (7.1).
2. `follow_up_enabled = true` → bật plugin `follow_up` trong `agent_plugin` với `config.channels` = kênh cũ.
3. Bỏ bảng `agent_follow_up` và hai cột `follow_up_*` của `agent_settings`. `downgrade`: tạo lại bảng và cột rỗng
   (không chép ngược).
4. Kèm (việc nhỏ chủ dặn): migration `crm_0002` của plugin `crm` bỏ index thừa `crm_reminder_sent_person`.

### 7.6 Đổi hành vi (chủ cần biết)

- Tin chăm sóc lại tính vào trần chung mỗi người mỗi ngày (cùng nhắc lịch); riêng nó tối đa 1 tin/người/ngày.
- Chăm sóc lại cần **cả** plugin `follow_up` bật **và** `cases_enabled` bật (công tắc khẩn tắt được nó).
- Mỗi ca tối đa 4 tin trong 14 ngày (hôm nay không có trần tổng, chỉ có 2 tin liền không trả lời); khách nhắn lại
  thì đếm "không trả lời" về 0 như hôm nay.
- **L7:** thêm plugin `follow_up` vào profile `clinic` là đổi danh sách T9 (`CLINIC_PLUGINS`). Chủ duyệt mục này là
  duyệt L7. Plugin không thêm tool, route, biến môi trường hay đường ra ngoài.

### 7.7 Test

- **Chép theo code:** test thuần của `test_follow_up.py` (`decide`, giờ nhắn, `asks_to_stop`, `parse_verdict`,
  `render_transcript`) sang `tests/follow_up/`.
- **Viết lại trên động cơ thật** (`InMemoryCaseStore`, model và kênh giả, như `test_crm_reminders.py`): im đủ lâu
  thì phán đoán đúng một lần; `done`/`hard_decline` không gửi; `hesitant` gửi đúng giờ, một lần; khách nhắn trước
  hẹn thì ca về `quiet`, không gửi; "đừng nhắn nữa" dừng ca; hai tin không trả lời thì dừng; ngoài giờ và hết chỗ
  trong ngày thì đợi; gửi lỗi quay về `check`; plugin tắt hoặc `cases_enabled` tắt thì không gửi; nhóm chat và
  kênh không theo dõi không mở ca.
- **Harness:** `ObservedMessage.user_id` của câu trả lời; `ctx.chat_history`.
- **DB (scratch):** migration 0007 chuyển hẹn sống thành ca, bật plugin; `test_ingress_db.py` bỏ phần follow-up.
- **Chạy lại:** T9 (`test_tool_allowlist.py`, thêm `follow_up` vào `CLINIC_PLUGINS`), `test_cases_engine.py`,
  `test_agent_settings.py`, `tests/zalo/`, `tests/crm/`; cả suite vì có migration.

### 7.8 Sau khi xanh

- Xóa dòng vi phạm trong `.claude/rules/agent-harness.md`; mục 3 bước 3 của kế hoạch này; HANDOFF; `infra/README.md`.
- `/diagram-design`: `pema-system-design.html` (bỏ `agent_follow_up`, bỏ hai cột). `/archify`: sơ đồ ca chăm sóc lại.

## 8. Bước 7: ngưỡng `run_turn` và nén ra cài đặt (mục 3 điểm 6; ghi 2026-10-23, chủ chốt hướng cùng ngày: cấu hình từ frontend; đã làm 2026-10-23, cả frontend theo lời chủ)

**Khác kế hoạch khi làm:** (1) `resolve_agent` dựng thử chính sách vòng lặp và nén, nên tổ hợp sai (ví dụ
`stop_after_repeats` không lớn hơn mốc nhắc lặp cuối của profile) bị từ chối khi lưu. (2) Nén vẫn cần
`[context] window_tokens` của profile để bật; cửa sổ của model chỉ thay số đó. (3) Cửa sổ của model đổi trên
giao diện có hiệu lực sau lần gọi model kế tiếp (`DynamicModel` đọc lại settings trước mỗi lần gọi, tối đa
5 giây một lần), nên lượt đầu sau khi đổi có thể còn dùng số cũ. (4) CLI có cờ cho mọi trường mới
(`agent settings set --max-steps ...`, `agent model set --window-tokens ...`). (5) Frontend: trang Cài đặt
thêm bốn nhóm (ca chủ động, ngân sách token, giới hạn mỗi lượt, nén), trang Model thêm ô cửa sổ ngữ cảnh.

### 8.1 Đọc code thấy gì (khác với DESIGN, chỗ nói "ngưỡng đang là hằng trong code")

- **Ngưỡng đã là dữ liệu, không còn viết cứng.** Mọi ngưỡng của vòng trong lượt và của nén nằm trong profile
  (`agent.toml`), có kiểm giới hạn (`profile.py`):
  - `[loop]`: `max_steps`, `max_output_tokens`, `max_turn_s`, `max_turn_tokens`, `repeat_thresholds`,
    `stop_after_repeats`, `error_streak_remind`, `error_streak_stop`, cách gom tin (`queue_*`);
  - `[context]`: `window_tokens`, `compact_at`, `keep_recent_ratio`, `chars_per_token`;
  - `[guards]`: `max_parallel_tools`, `max_tool_calls_per_step`.
  Hằng còn lại trong `agentcore` (`FLUSH_STEPS`, `SUMMARY_OUTPUT_TOKENS`, `TRANSCRIPT_BLOCK_CHARS`,
  `MESSAGE_OVERHEAD_TOKENS`…) là chi tiết cách làm, không phải ngưỡng ai cần chỉnh: giữ nguyên.
- **Đã có quyết định cũ là để chúng trong profile:** docstring `agent_settings.py`: "guards, loop, context… là giới
  hạn của dịch vụ, không phải lựa chọn của người vận hành phòng khám". Đưa cả khối lên trang cài đặt (DB) là đảo
  quyết định đó, và cho người vận hành nới trần mà chủ đặt.
- **Lỗ thật: cửa sổ ngữ cảnh không theo model.** Model đổi được trên giao diện (`agent_model_entry`,
  `agent_model_settings`), nhưng `window_tokens` cố định trong profile (`clinic`: 128000). Đổi sang model cửa sổ
  nhỏ hơn (ví dụ 32k) thì agent không nén tới khi vượt 96k token, và model trả lỗi quá cửa sổ ở các cuộc chat dài.
  Ngược lại, model cửa sổ lớn bị nén sớm vô ích.

### 8.2 Chủ chốt (2026-10-23)

Ngưỡng cấu hình được từ frontend (trang cài đặt agent), đổi có hiệu lực từ lượt kế tiếp, không khởi động lại. Đảo
quyết định cũ trong docstring `agent_settings.py` ("guards, loop, context… ở profile"): sửa docstring đó.
Hằng trong `agentcore` (8.1) giữ nguyên trong code.

### 8.3 Ngưỡng của agent: `agent_settings`, cùng cách `memory_*`, `cases_enabled`, `tokens_*`

1. Trường mới (NULL = lấy profile; giới hạn y như `profile.py` hôm nay, kiểm ở code, ở `PATCH` và CHECK ở DB):

   | Nhóm | Trường | Giới hạn |
   |---|---|---|
   | Vòng trong lượt | `max_steps` | 1–50 |
   | | `max_output_tokens` | 64–32 768 |
   | | `max_turn_s` | 10–1 800 |
   | | `max_turn_tokens` | 1 000–10 000 000, NULL = không trần |
   | Chống lặp, lỗi | `stop_after_repeats`, `error_streak_stop` | 2–50 |
   | Nén | `compact_at` | 0.3–0.95 |
   | | `keep_recent_ratio` | 0–0.6 |
   | Tool | `max_parallel_tools` | 1–32 |
   | | `max_tool_calls_per_step` | 1–64 |

   Không đưa lên: `repeat_thresholds`, `error_streak_remind` (lời nhắc model, hiếm khi chỉnh), `chars_per_token`
   (ước lượng kỹ thuật), các `queue_*` (cách gom tin theo kênh, gắn với kênh).
2. `resolve_agent` đặt chúng lên `Profile` (`loop`, `context`, `guards`) như đang làm với `memory`; `show()` trả giá
   trị đang dùng và `sources` (db / profile); `PATCH /v1/admin/settings` nhận chúng; `--clear` của CLI trả về
   profile. Đổi xong thì `AgentSettings` dựng lại agent ở lượt kế tiếp (đường sẵn có).
3. Migration `0008_agent_limits.{sql,py}`: các cột trên của `agent_settings`, CHECK theo bảng; `downgrade` bỏ cột.

### 8.4 Cửa sổ ngữ cảnh theo model: trên trang model

1. `agent_model_entry` và `agent_model_settings` thêm `window_tokens integer` (NULL được, CHECK 4 000 – 2 000 000),
   cùng migration 0008. Route model (`/v1/admin/model`, danh sách model) nhận và trả trường này; chọn một model trong
   danh sách thì chép cả `window_tokens` như các trường khác.
2. Model đổi lúc đang chạy mà không dựng lại agent (`DynamicModel`), nên `ContextManager` đọc cửa sổ lúc kiểm nén:
   nhận `window: Callable[[], int | None]` (lõi, chung, H10). `assembly.py` đưa vào hàm: cửa sổ của model đang dùng,
   không có thì `window_tokens` của profile, không có cả hai thì không nén như hôm nay.
3. Bỏ được `[context] window_tokens` trong profile? Không: giữ làm mặc định cho model chưa khai.

### 8.5 Frontend

Phiên frontend (Claude khác) giữ `pema-agent/frontend`; tôi không sửa. Sau khi backend xanh: sinh lại OpenAPI ở
backend, ghi cho phiên đó danh sách trường, giới hạn, nhóm và chữ hiển thị đề xuất (vào `HANDOFF` hoặc file bàn giao
nó đọc). Trước khi có giao diện, đặt được qua `PATCH` hoặc CLI.

### 8.6 Test

- Settings: mỗi trường lưu, đọc, trả về profile khi xóa; ngoài giới hạn bị từ chối ở code, ở `PATCH` (422) và ở DB.
- Agent dựng lại theo giá trị mới ở lượt kế tiếp (`max_steps` hạ thì lượt dừng sớm hơn).
- Lõi: ngưỡng nén tính theo cửa sổ hàm trả về lúc gọi; đổi model giữa hai lượt thì ngưỡng đổi theo.
- Model: `window_tokens` lưu, chép từ danh sách, ngoài giới hạn bị từ chối.
- DB (scratch): migration 0008 lên, xuống. Chạy cả `apps/agent` + `packages` vì có migration.

### 8.7 Sau khi xanh

- `/diagram-design`: cột mới trên `pema-system-design.html`; ERD archify `agent_rt`.
- HANDOFF, `infra/README.md`; bàn giao cho phiên frontend (8.5).
