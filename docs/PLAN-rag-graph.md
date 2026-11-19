# Kế hoạch: đồ thị của lượt trả lời, và agentic RAG có kiểm, có sửa

Trạng thái: **bản 1 (2026-11-19), chờ chủ duyệt.** Nhánh `split/agent`. Gồm bước 15–18 của lộ trình tách ngày
2026-11-18: thước đo câu trả lời, đồ thị của lượt (khái niệm mới ở lõi), luồng RAG của plugin `knowledge` trên đồ thị đó,
đo lại. Vòng tự cải thiện kho (bước 19) và gỡ chữ "phòng khám" (bước 20) có kế hoạch riêng sau.

Luật áp: H1–H11 (`.claude/rules/agent-harness.md`), L1–L7 (`.claude/rules/agent-crm-boundary.md`). Đây là khái niệm mới
ở lõi nên theo H10, H11: chủ nói "go" mới code.

## 1. Vì sao

- **Đã có agentic RAG mức cơ bản.** Model tự gọi `kb_search` (kèm tối đa hai cách hỏi khác), tự đọc thêm bằng `kb_read`;
  tìm lai từ khóa và vector; Jev chấm từng đoạn và từ chối khi không đoạn nào có bằng chứng; mở đoạn nhỏ ra mục cha.
- **Thiếu hai vế cuối của công thức harness: Verification và Correction.** Không có gì kiểm câu trả lời trước khi gửi.
  Con số model viết ra (giá, số buổi, số ngày, phần trăm) không ai đối chiếu với đoạn tìm được. Lời dặn trong prompt
  ("con số phải lấy đúng như trong đoạn") là việc của model, không phải của code (H4).
- **Không làm được bằng hook hiện có.** Hook sau model (`PostModelHook`) chỉ sửa được câu trả lời, không bảo model viết
  lại được. "Sai thì quay lại sửa, tối đa một lần" là một cạnh quay lui có bộ đếm, tức là việc của đồ thị (H2, H3).
- **Chậm vì model phải tự nhớ đi tìm.** Một câu hỏi về giá thường tốn 2–4 lần gọi model: một lần để quyết định gọi
  `kb_search`, một lần sau khi có kết quả, thêm lần nữa nếu tìm lại hay đọc thêm. Code tìm trước thì model chỉ còn việc
  viết.
- **Chưa đo được câu trả lời.** `scripts/kb_bench.py` đo "tìm có đúng tài liệu không", chưa đo "trả lời có đúng không".
  Không có thước đo này thì không biết đồ thị có giúp gì.

## 2. Đã có gì để dùng lại

| Có sẵn | Ở đâu | Dùng cho |
|---|---|---|
| Hình đồ thị: `Graph`, `Edge` (điều kiện, bộ đếm, cạnh lỗi), kiểm cạnh quay lui | `agentcore.cases.spec` | Hình của đồ thị lượt; phần kiểm tách ra dùng chung |
| Vòng trong: gọi model, thử lại, chạy tool, cất lịch sử, nén, trần bước, trần giờ, trần token, loop guard, steer | `agentcore.loop.run_turn` | Nút model của đồ thị chạy đúng các mảnh này |
| Mẫu "câu trả lời chưa gửi" (`UNSENT_NOTE`) và `RetryObserver.retry` | `run_turn` | Lần sửa: lịch sử vẫn hợp lệ, console xóa bản nháp đang hiện |
| Tìm kiếm và chấm: `Searcher.search(...)`, `JudgePlan`, `JudgeOutcome.kept` | `plugins/knowledge/search.py`, `judging.py` | Nút tìm bằng code |
| Hook `pre_model` đưa kịch bản vào câu hỏi | `plugins/conversations/scenarios.py` | Tiền lệ: harness lấy dữ liệu trước model |
| Trace mỗi lượt, trang Trace | `agentcore.trace`, `traces-page.tsx` | Thấy từng nút đã chạy, vì sao rẽ |
| 22 tài liệu demo, 38 câu hỏi có `expect` và `facts`, bảng 76 dữ kiện có giá trị chuẩn | `E:/Desktop/data test/AgentRAG_Pema_Demo`, `scripts/kb_bench_pema.jsonl` | Chấm câu trả lời bằng code |

## 3. Bước 16 (làm trước): thước đo câu trả lời

Script mới `apps/agent/scripts/rag_bench.py`, chạy ngoài Docker như `kb_bench.py` (không phải unit test; luật
`test-writing.md` không cấm công cụ đo).

- **Nạp:** 22 tài liệu vào `InMemoryKnowledgeStore` bằng đúng đường nạp của `kb_bench.py`; embedding thật nếu có
  `BEEKNOEE_API_KEY`, Jev nếu có `TYPESAFE_API_KEY`.
- **Hỏi:** mỗi câu chạy một `run_turn` thật (model thật, khóa đọc từ biến môi trường, không in ra), mỗi câu một phiên
  mới. Thêm vào bộ câu hỏi: 6 câu nối tiếp hai lượt ("trị nám bao nhiêu" rồi "còn gói 10 buổi?"), 4 câu thử giá cũ và
  bản nháp (bật `benchmark_mode`), 4 câu chào hỏi không cần tra (để đồ thị không biến chúng thành "chưa có thông tin").
- **Chấm bằng code**, không cần model:
  - *Đúng dữ kiện*: giá trị chuẩn của từng mã trong `facts` có trong câu trả lời (chuẩn hóa số: `25.000.000`,
    `25 triệu`, `25tr` là một).
  - *Bịa số*: con số trong câu trả lời không có trong bất kỳ tài liệu nào, không có trong câu hỏi và không phải ngày giờ
    hiện tại.
  - *Từ chối đúng* (tập C): không nêu con số nào và nói chưa có thông tin.
  - *Chi phí*: số lần gọi model, token vào và ra, thời gian của lượt (lấy từ `TurnTrace`).
- **Chấm thêm bằng Jev** (tùy chọn `--judge`): "câu trả lời có khẳng định điều gì mà các đoạn không nói không".
- **Ra:** bảng theo từng tập (A, B, C, nối tiếp, thử thách, chào hỏi) và file JSON để so hai lần chạy.
- **Chạy hai chế độ:** `--graph off` (như hôm nay) và `--graph on`. Lần đầu chỉ chạy `off` để có **số gốc**.
- Chi phí ước tính một lần chạy: khoảng 52 câu × 3 lần gọi model; với DeepSeek dưới 0,5 USD. Jev khoảng 0,02 USD.

## 4. Bước 17a (lõi): đồ thị của lượt

Một khái niệm chung (H10): **lượt trả lời khách có thể chạy theo một đồ thị do plugin khai báo**. Lõi không biết RAG là
gì; nó chỉ chạy nút và đi theo cạnh.

### 4.1 Hình (`agentcore.turns`, thuần: pydantic và stdlib)

```python
TurnGraphSpec(
    name="knowledge_answer",          # a-z0-9_
    state_model=RagState,             # BaseModel của plugin; lõi chỉ đọc các bộ đếm
    graph=Graph(start="search", nodes=(...), edges=(...)),   # dùng lại Graph, Edge của agentcore.cases
    counters={"rewrites": 1, "revisions": 1},                # trần của từng bộ đếm (H3)
)
CodeStep(id, run)        # run(state, view) -> Step(patch, next=None, note="") ; view: câu hỏi, lịch sử đọc được, giờ
ModelStep(id, instruction, tools=None, max_steps=None, after=None)
                         # một lần chạy vòng trong; instruction(state) -> lời dặn đi trong khối ngữ cảnh của lượt
                         # tools=None: mọi tool của agent; () : không tool. after(state, outcome) -> patch
SendStep(id, text=None)  # kết thúc: gửi bản nháp cuối, hoặc text(state) do code viết
```

- `outcome` của một `ModelStep`: văn bản model viết, các kết quả tool của bước đó (tên tool, nội dung), token.
- **Kiểm khi dựng** (như `CaseSpec._check`, H3): tách phần kiểm đồ thị của `cases.spec._check` thành một hàm dùng chung
  (`agentcore.graph_rules`): id duy nhất, nút bắt đầu có thật, cạnh trỏ tới nút có thật, **cạnh quay lui phải có bộ
  đếm có trần**, ít nhất một `SendStep` tới được từ nút bắt đầu, mọi nhánh đều tới được một `SendStep`. Không nới phần
  kiểm hiện có của `CaseSpec`.

### 4.2 Chạy (trong `run_turn`, tham số mới `graph`)

- Không có `graph`: `run_turn` chạy như hôm nay, từng dòng không đổi.
- Có `graph`: thay vòng `for step in range(max_steps)` bằng vòng đi nút. Mọi trần của lượt vẫn áp chung cho cả đồ thị:
  `max_steps` (tổng số lần gọi model), `max_turn_s`, `max_turn_tokens`, loop guard, steer. Thêm `max_nodes` (mặc định
  12) để vòng đi nút luôn dừng (H3).
- `CodeStep` chạy code của plugin; lỗi của nó đi theo cạnh `on="error"` nếu có, không thì lượt chạy như không có đồ thị
  (đi thẳng vào nút model trả lời với lời dặn rỗng). Đồ thị hỏng không bao giờ làm khách mất câu trả lời.
- `ModelStep` dùng đúng `call_model`, `executor`, `record` của `run_turn`. Câu trả lời của nó là **bản nháp**: được cất
  vào lịch sử như mọi tin của assistant, nhưng chưa phải là câu trả lời của lượt.
- **Sửa bản nháp:** khi đồ thị quay lại một `ModelStep`, lõi cất một tin `[System] ...` (cùng kiểu `UNSENT_NOTE`):
  "câu trả lời trên chưa được gửi vì ...; viết lại", kèm lý do do code viết. Lịch sử luôn hợp lệ, model thấy vì sao.
  Console đang hiện bản nháp nhận `observer.retry("checked")` để xóa nó.
- `SendStep`: câu trả lời của lượt là bản nháp cuối, hoặc văn bản code viết (`text(state)`; khi đó cất thành tin
  assistant). `TurnResult` không đổi hình.
- Trace: mỗi nút một `TraceEvent("node", ...)` (tên nút, cạnh đã đi, bộ đếm, ghi chú ngắn của plugin; chỉ siêu dữ liệu,
  không chép nội dung). `stop` mới: `"graph"` khi `max_nodes` hết.

### 4.3 Nối vào agent

- Plugin khai báo bằng `ctx.register_turn_graph(spec)`. Mỗi agent **tối đa một** đồ thị đang bật; plugin thứ hai khai
  báo thì plugin đó không nạp được (báo rõ tên). Lõi và dispatcher không gọi tên plugin nào (H1).
- Dispatcher truyền `graph=agent.turn_graph` cho **lượt của khách**. Lượt của ca (`TurnNode`, tin chủ động) vẫn chạy như
  cũ (H8). Lượt trong nhóm chat cũng chạy đồ thị.
- Tắt đồ thị là không khai báo nó: prompt và danh sách tool không đổi, vân tay cache không đổi (H9).

## 5. Bước 17b (plugin `knowledge`): luồng RAG

Cài đặt mới của plugin: `answer_graph` = `off` (mặc định) | `observe` | `on`.

```
search (code) ──có bằng chứng──────────────────────────────► answer (model)
   │  └─không có, rewrites < 1 ─► rewrite (model, không tool) ─┘ (về search, +1 rewrites)
   └─không có, rewrites = 1 ───────────────────────────────► answer (lời dặn: không có dữ kiện)
answer ──► check (code) ──đúng──────────────────────────────► send
               ├─sai, revisions < 1 ─► answer (+1 revisions, lý do do code viết)
               └─sai lần hai ─► safe_answer (model, lời dặn: không nêu con số) ─► check_safe (code)
                                    ├─đúng ─► send
                                    └─sai ─► send_fixed (câu cố định do code viết)
```

- **search** (code): câu tìm = tin mới nhất của khách; tin ngắn (dưới 6 từ) thì ghép thêm tin trước đó của khách (câu
  nối tiếp). Chạy `Searcher.search` với embedding và Jev như `kb_search`. `found` = Jev giữ lại ít nhất một đoạn
  (Jev tắt: có đoạn qua ngưỡng điểm). Ghi đoạn và mã tài liệu vào state.
- **rewrite** (model, không tool, 1 bước): viết lại câu hỏi cho đủ ý từ ngữ cảnh cuộc chat, cộng tối đa hai cách hỏi
  khác, dạng JSON. Code đọc JSON (sai dạng thì bỏ qua, coi như không tìm lại được) rồi quay về `search`.
- **answer** (model, mọi tool của agent, tối đa 3 bước): lời dặn mang khối "Dữ kiện tìm được" (đoạn, mã tài liệu, ngày
  hiệu lực) và quy tắc: chỉ nêu con số có trong khối hoặc trong kết quả tool của lượt này. Không có dữ kiện thì lời dặn
  nói rõ: câu hỏi cần dữ kiện phòng khám thì nói chưa có thông tin và mời để lại liên lạc; câu chào hay câu không cần
  tra thì trả lời bình thường. Model vẫn gọi được `kb_read`, `kb_search` và các tool khác: đây vẫn là agentic RAG, chỉ
  là bước tìm đầu tiên do code làm.
- **check** (code, H4, H5): lấy mọi con số trong bản nháp (số có dấu chấm, phẩy, `tr`, `k`, `%`, ngày `dd/mm`); mỗi số
  phải có trong: các đoạn của state, kết quả tool của lượt, tin của khách trong lượt, hoặc ngày giờ của lượt. Bỏ qua số
  thứ tự đầu dòng (`1.`, `2)`). Số lạ thì lý do là "các số X, Y không có trong dữ kiện". Không gửi số lạ cho khách.
- **safe_answer** và **send_fixed**: lần cuối model viết không con số nào; sai nữa thì gửi câu cố định trong cài đặt
  `unsure_reply` (mặc định "Dạ em chưa có thông tin chắc chắn cho câu này, em chuyển nhân viên hỗ trợ mình ạ.").
- **Chế độ `observe`:** lượt chạy như `off` (không đồ thị); sau lượt, plugin chạy `check` trên câu trả lời đã gửi bằng
  một hook sau lượt và chỉ ghi vào trace số con số lạ. Dùng để đo trên hội thoại thật trước khi bật `on`.

Số lần gọi model ước tính mỗi câu hỏi: `on` thường 1 (answer), 2 khi tìm lại hoặc sửa, tối đa 4
(rewrite + answer + answer + safe_answer). Hôm nay thường 2–4.

## 6. Bước 18: đo lại và quyết định

- Chạy `rag_bench.py --graph on` trên cùng bộ câu hỏi, so với số gốc.
- **Ngưỡng để bật `on` mặc định cho profile `rag`** (chủ quyết lại khi thấy số): bịa số giảm, đúng dữ kiện không giảm quá
  1 câu, tập C không xấu đi, tập chào hỏi không bị trả lời "chưa có thông tin", thời gian trung vị của lượt không tăng.
- Không đạt thì giữ `off`, ghi kết quả vào mục 9 của file này, sửa theo số rồi đo lại.

## 7. Vòng và cách chặn

| Vòng | Chặn bằng |
|---|---|
| search ↔ rewrite | bộ đếm `rewrites`, trần 1; vượt thì đi `answer` không dữ kiện |
| check → answer | bộ đếm `revisions`, trần 1; vượt thì đi `safe_answer` |
| safe_answer → check_safe | không quay lui: `check_safe` chỉ đi tới `send` hoặc `send_fixed` |
| Đồ thị nói chung | `max_nodes` (12), `max_steps`, `max_turn_s`, `max_turn_tokens` của lượt; kiểm khi dựng: cạnh quay lui phải có bộ đếm, mọi nhánh tới được `SendStep` |
| Lỗi của nút code | cạnh `on="error"`, không có thì lượt chạy như không có đồ thị |
| Jev hay embedding chậm, hết hạn mức | `search` đi tiếp với từ khóa và đoạn chưa chấm, như `kb_search` hôm nay |

## 8. Đối chiếu luật

- **H1:** hình ở `agentcore.turns` (thuần), chạy ở `run_turn` (lõi, không biết plugin), nội dung ở plugin `knowledge`.
  `knowledge` không import plugin khác; Jev vẫn đi qua dịch vụ `judge` của `plugin_kit`.
- **H2:** nút, cạnh, điều kiện, bộ đếm, trần là dữ liệu khai báo; `Edge.when` và `CodeStep.run` là hàm, đổi được thành
  biểu thức dữ liệu sau này như đồ thị ca.
- **H3:** kiểm khi dựng, bộ đếm có trần, `max_nodes`; phần kiểm của `CaseSpec` không nới.
- **H4:** code quyết tìm hay không, có dữ kiện hay không, con số có được phép không, khi nào thôi sửa; model chỉ viết.
- **H5:** `check` là bước kiểm bằng code chạy ngay trước `send`, kể cả sau lần sửa.
- **H7:** đồ thị chạy trong một lượt, không có trạng thái bền mới; bản nháp và tin `[System]` nằm trong lịch sử như hôm
  nay.
- **H8:** chỉ lượt của khách; lượt của ca không đổi.
- **H9:** `off` không đổi prompt, tool hay cache. `on` đổi khối ngữ cảnh của lượt (không đổi system prompt đã đông
  cứng), nên cache của phần system vẫn giữ.
- **H10:** "lượt chạy theo đồ thị" dùng được cho mọi plugin (ví dụ một luồng đặt lịch có kiểm), không phải ngoại lệ
  cho RAG.
- **L1, L2, L4, L6:** không có đường dữ liệu mới, không tool ra internet mới. **L7:** không thêm tool; cài đặt mới của
  plugin `knowledge` (`answer_graph`, `unsure_reply`) không phải tool.

## 9. Các bước và cách kiểm

| # | Việc | Xong khi |
|---|---|---|
| 1 | `rag_bench.py`, câu hỏi mới, chạy `--graph off` | Có bảng số gốc, ghi vào mục 10 |
| 2 | `agentcore.turns`, tách phần kiểm đồ thị dùng chung | Đồ thị sai luật không dựng được; `CaseSpec` vẫn dựng các ca hiện có |
| 3 | `run_turn(graph=...)`, `register_turn_graph`, dispatcher | Agent khởi động; không có đồ thị thì lượt y như cũ |
| 4 | Luồng RAG của `knowledge`, cài đặt `answer_graph`, `unsure_reply` | `bun run build` qua, agent khởi động với `answer_graph=on` |
| 5 | Trace: sự kiện `node`, nhãn "Bước đồ thị" ở trang Trace | Trang Trace hiện các nút của một lượt |
| 6 | E2E `agent-rag-graph.spec.ts`: bật `on` ở trang Kho tri thức, gửi một câu hỏi qua `/agent/v1/chat`, mở Trace thấy các nút `search`, `answer`, `check` | Chủ chạy qua |
| 7 | `rag_bench.py --graph on`, so với số gốc | Bảng so sánh; chủ quyết bật mặc định hay không |

Không viết unit test (luật `test-writing.md`). Sau bước 7 vẽ lại sơ đồ luồng một lượt bằng `/archify` (luật
`diagram-after-task.md`).

## 10. Kết quả đo

(Chưa chạy.)

## 11. Câu hỏi còn mở (chủ quyết)

1. **Câu cố định khi không chắc** (`unsure_reply`): chuyển nhân viên như mặc định ở trên, hay chỉ nói chưa có thông
   tin? Stack hiện không có CRM nên "chuyển nhân viên" chỉ là lời nói, chưa có ai nhận.
2. **Câu nối tiếp:** ghép tin trước của khách khi tin mới dưới 6 từ là cách rẻ (không tốn lần gọi model). Nếu bước đo
   cho thấy hụt nhiều, thay bằng `rewrite` chạy ngay từ đầu cho tin ngắn (thêm 1 lần gọi model cho các tin đó).
3. **Bản nháp bị chặn có nằm trong lịch sử không:** kế hoạch giữ nó (như tin chưa gửi khi khách nhắn chen), để lịch sử
   hợp lệ và model thấy vì sao phải viết lại. Cách khác là bỏ bản nháp khỏi lịch sử, sạch hơn nhưng phải xử lý riêng các
   cặp tool của nút đó.
4. **Tiền cho bước đo:** khoảng 0,5 USD mỗi lần chạy với DeepSeek, cần khóa model trong biến môi trường máy chạy.
