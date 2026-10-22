# Kế hoạch: vòng ngoài theo ca (case loop), bước 1 và 2

Ghi 2026-10-22. Thiết kế gốc: `DESIGN-case-loop.md`. Chủ duyệt 2026-10-22: làm `case_done` và `case_wait_until`
trước; `case_need_human` để sau. Lời duyệt đó cũng là duyệt L7 cho hai tool mới trong profile `clinic`.
**Trạng thái (2026-10-22): bước A và B đã làm.** Khác kế hoạch khi làm: `TurnNode` bỏ `sends` (một câu trả lời
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

1. Ngân sách token theo phiên và ngày trước `run_turn` (DESIGN mục 3 bước 1).
2. Hợp đồng `JudgeService`, `EmbeddingService` ra package trung lập.
3. **Chăm sóc lại thành plugin `follow_up` trên động cơ** (DESIGN 2.5). Lý do chưa làm ngay: route
  `/v1/admin/follow-ups` và hai trường `follow_up_*` của settings đang được frontend dùng, mà frontend do phiên
  Claude khác giữ; đổi cùng lúc với phiên đó.
4. Nhắc lịch của `crm` lên động cơ (DESIGN 2.6).
5. `case_need_human`, `HumanNode`, route `resume`/`close`, giao diện nhân viên.
6. Ngưỡng `run_turn` và nén ra cài đặt.

## 4. Rủi ro ghi trước

- Động cơ không có ca nào chạy cho tới khi một plugin `register_case`: sau bước B, hệ chạy y như cũ (hai tool có
  trong registry nhưng trả lỗi "không có ca" khi model gọi ngoài ca). Prompt của model đổi vân tay (thêm hai tool)
  → mọi phiên dựng lại system prompt một lần, có log cache break; chấp nhận.
- Quyết định của tool ghi trong RAM của tiến trình (mục 0): mất khi lượt bị tiến trình khác vớt.
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
