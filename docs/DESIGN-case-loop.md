# Thiết kế: vòng ngoài của agent theo "ca" (case), độc lập với plugin

Ghi 2026-10-22. Trạng thái: **thiết kế, chưa làm**; làm khi chủ nói "go". Phần 1 là câu trả lời gốc giữ nguyên
để không mất khi nén ngữ cảnh. Phần 2 là schema. Phần 3 là thứ tự làm. Khung gốc của chủ: `IDEAS-agent-loops.md`
mục 1 và 5 (một vòng = cái gì khởi động + cái gì kết thúc; năm phần trigger, goal, verify, stop, memory).

---

## 1. Câu trả lời gốc (giữ nguyên lời)

### 1.1 Ý định: để hệ chuẩn Agent = LLM + Harness (prompt, context, loop, graph)

- **Prompt engineering: đã chuẩn, không đụng.** System prompt đóng băng theo phiên kèm vân tay, section lõi và
  section plugin tách bạch, phần hay đổi nằm trong khối context cuối yêu cầu.
- **Context engineering: đã chuẩn, chỉ còn chuyển ngưỡng ra cài đặt.** Nén, flush memory trước khi tóm tắt, ghi
  chú sống qua phiên đều nằm ở agentcore. RAG đã là plugin `knowledge`. Ngưỡng nén và giới hạn của run_turn đang
  là hằng trong code, sau này chuyển lên cài đặt. Làm sau cùng.
- **Loop engineering: đây là chỗ phải làm.** Hiện có một vòng trong lượt (run_turn, đã tốt) và hai vòng ngoài
  lượt chạy bằng hai động cơ riêng: chăm sóc lại nằm cứng trong agent_app, nhắc lịch nằm trong plugin crm.
- **Graph engineering: không viết code, chỉ chừa chỗ.** Trạng thái và chuyển tiếp của vòng là dữ liệu, không cứng
  trong hàm, để graph sau này cắm vào cùng động cơ.
- Không đụng: luật L1–L7, danh sách tool đã duyệt, frontend, tool memory ở lõi.

### 1.2 Loop engineering "như Claude Code" là gì (trả lời câu "tôi chỉ cần nhắn task là bạn tự xử tới goal")

Tôi nói từ chính cách tôi đang chạy, rồi dịch sang hệ của bạn.

**Vì sao tôi "tự làm tới goal" được.** Không có vòng nào thần kỳ. Có bốn thứ cộng lại:

1. **Goal nằm trong context suốt vòng.** Tin bạn nhắn là goal. Nó không bị mất qua mọi bước, kể cả sau khi nén.
2. **Tôi có tool để tự kiểm.** Chạy test, đọc file, xem git. Vòng tiếp tục vì tôi thấy kết quả rồi tự quyết bước
   sau. Kiểm là tool, không phải vòng riêng.
3. **Harness chỉ quyết hai thứ: khi nào gọi tôi lại, khi nào cấm tôi chạy nữa.** Nó gọi lại khi tool trả kết quả,
   khi tác vụ nền xong, khi tới giờ hẹn. Nó dừng cứng khi hết bước, hết tiền, hết giờ. Còn "xong chưa" thì tôi tự
   nói, bằng cách trả lời không gọi tool nữa.
4. **Chờ là một trạng thái, không phải kết thúc.** Khi tôi phải đợi CI hay đợi bạn, tôi ghi trạng thái, hẹn giờ
   thức, và vòng tiếp tục ở lần gọi sau với cùng goal và cùng trạng thái.

**Hệ của bạn hiện thiếu gì.** `run_turn` đã có điểm 2 và 3 ở mức một lượt. Nhưng vòng ngoài (chăm sóc lại, nhắc
lịch) đang đi đường khác: code quyết hết, model chỉ viết câu chữ. Cách đó an toàn và rẻ, hợp với nhắc lịch. Nhưng
nó không cho "nhắn một câu là agent tự xử tới goal", vì không có chỗ nào giữ goal qua nhiều lần đánh thức, và model
không có cách nói "xong", "chờ", "cần người".

**Định nghĩa tôi đề xuất: Ca (case).** Một ca là một goal đang sống, gồm đúng năm phần dữ liệu:

- `goal`: một câu, kiểm được bằng dữ liệu. Ví dụ: "khách này xác nhận hoặc hủy lịch X".
- `trigger`: cái gì đánh thức ca (sự kiện CRM, tin của khách, giờ hẹn).
- `state`: bản ghi có kiểu mà mọi lần chạy cùng đọc ghi (lịch, version, số tin đã gửi, câu trả lời cuối).
- `stop`: điều kiện kết thúc cứng, do code kiểm (đạt goal, quá hạn, hết lượt, khách bảo thôi, công tắc tắt).
- `verify`: đọc lại đâu để biết đạt goal chưa (tool `my_appointments`).

**Và ba tool điều khiển cho model**, đây là chỗ giống Claude Code nhất: `case_done(reason)`,
`case_wait_until(when, why)`, `case_need_human(why)`. Model dùng tool của plugin để hành động, dùng ba tool này để
điều khiển vòng. Động cơ ở agent_app chỉ làm việc máy: nhận trigger, nạp ca vào context, gọi run_turn, lưu state,
chống trùng, đếm ngân sách, áp stop, ghi nhật ký quyết định.

**Hai kiểu nút trên cùng động cơ.** Nút "code quyết" (nhắc lịch: `decide` thuần, không gọi model) và nút "model
quyết" (chăm sóc lại: model đọc hội thoại rồi chọn). Graph của bạn sau này chính là thứ tự các nút và cạnh có điều
kiện giữa chúng. Vòng = đồ thị có ít nhất một cạnh quay lại trigger, mỗi cạnh quay lại có bộ đếm trong state.

Khác biệt duy nhất với Claude Code: vòng của tôi kéo dài vài phút trong một phiên, vòng của phòng khám kéo dài nhiều
ngày và đợi người thật. Nên `wait` và `need_human` phải lưu xuống DB, không nằm trong RAM.

Chưa kiểm lúc viết: một ca có gọi `run_turn` theo cùng khóa phiên với tin của khách không. **Đã kiểm sau đó:** tin
chủ động đi qua `Dispatcher.accept` → cùng hàng đợi `agent_ingress` → cùng `SessionLocks.hold(session_id)`
(`agent_app/dispatcher.py:226`). Rủi ro: ca do model điều khiển tốn token hơn vòng code thuần, nên ngân sách theo
ca phải có trước khi bật.

### 1.3 So với hình IBM (Schedule/Hook → Goal → Action → Observe → Adjust → Goal; Tool dưới Action; Subagent dưới Observe)

Giống. Đối chiếu:

| Trong hình | Ở Claude Code | Ở hệ này |
|---|---|---|
| Schedule, Hook → Goal | Tin người dùng nhắn, giờ hẹn thức, tác vụ nền báo xong | Sự kiện CRM, tin Zalo, mốc giờ |
| Goal | Task giữ trong context suốt vòng | Chưa có: bảng ca ở mục 2 |
| Action → Tool | Gọi tool | `run_turn` gọi tool plugin; crm đi qua crm-signer |
| Observe | Kết quả tool | Kết quả tool, và sự kiện CRM báo về sau |
| Adjust → Goal | Model đọc kết quả, chọn bước sau | Nút model quyết, hoặc nút code quyết (`decide`) |
| Subagent | Agent con làm rồi báo lại | Lời gọi model phán đoán của chăm sóc lại |

Hai thứ hình bỏ qua mà phòng khám không bỏ được: (1) **lối ra**: vòng vẽ kín; thực tế lối ra là model trả lời không
gọi tool nữa cộng chặn cứng (hết bước, hết tiền, hết giờ, người bảo thôi); (2) **chỗ chờ**: Observe của phòng khám có
thể là "đợi khách ba ngày", nên trạng thái phải nằm trong DB và "chờ" là một trạng thái tử tế. Subagent nên coi là một
Action đặc biệt, kết quả quay về như mọi quan sát khác; điểm này không đổi thiết kế.

---

## 2. Schema

### 2.1 Ba tầng, chiều import một chiều

| Tầng | Gói | Giữ gì | Không được giữ |
|---|---|---|---|
| Hình | `agentcore.cases` (mới) | Kiểu dữ liệu của ca, nút, cạnh, luật dừng, quyết định; hàm thuần `apply`, `blocked`, `next_node` | DB, model, HTTP, tên plugin |
| Chạy | `agent_app/cases/` (mới) | Store Postgres, `CaseEngine` (job nền), lắp ba tool điều khiển, route admin | Nội dung của bất kỳ ca nào |
| Nội dung | plugin (`plugins/follow_up`, `plugins/crm`) | `CaseSpec`: goal, trigger, state model, nút, cạnh, luật dừng, ngân sách | Hàng đợi, khóa, đếm, nhật ký |

Chiều import: plugin → `agent_app.plugins` → `agentcore`. Test T9 thêm kiểm cấu trúc: `agentcore` không import
`agent_app` hay `plugins`; `agent_app` không import `plugins.*`.

### 2.2 Hình của một ca (`agentcore.cases`, thuần, pydantic + stdlib)

```python
CaseStatus = Literal["open", "waiting", "needs_human", "done", "stopped"]
WaitFor    = Literal["customer", "clock", "event", "human"]

class Trigger:            # cái gì đánh thức: đúng một trong ba
    kind: Literal["clock", "customer_message", "event"]
    event: str | None     # kind="event": tên sự kiện plugin phát, vd "crm.appointment.changed"

class StopRules:          # chặn cứng, code kiểm trước MỖI nút
    max_turns: int                 # lượt model của ca
    max_proactive: int             # tin chủ động của ca
    max_age: timedelta             # tuổi tối đa của ca kể từ lúc mở
    counters: dict[str, int]       # trần cho từng bộ đếm trong state, vd {"unanswered": 2}

class Budget:
    tokens: int | None             # input + output của ca
    per_person_per_day: int        # tin chủ động một người nhận trong một ngày, DÙNG CHUNG mọi ca

class CodeNode:           # code quyết, không gọi model
    id: str
    run: Callable[[State, datetime], Decision]

class TurnNode:           # model quyết: một lượt run_turn của phiên khách, có ba tool điều khiển
    id: str
    instruction: Callable[[State, datetime], str]   # goal + tình trạng, đặt đầu tin kèm dấu [Hệ thống · <ca>]
    sends: bool = True                              # trả lời đi tới khách (SKIP thì không), hay chỉ phán đoán

class HumanNode:          # dừng chờ nhân viên; nhân viên bấm "tiếp" hoặc "đóng"
    id: str
    why: Callable[[State], str]

class Edge:
    src: str
    dst: str
    when: Callable[[State], bool] | None   # None = cạnh mặc định
    counter: str | None                    # BẮT BUỘC khi dst đứng trước src (cạnh quay lại): tên bộ đếm trong state

class Graph:
    start: str
    nodes: list[CodeNode | TurnNode | HumanNode]
    edges: list[Edge]

class Decision:           # kết quả của một nút
    next: str | None = None              # nút kế; None = theo cạnh
    wait_for: WaitFor | None = None      # "waiting" tới khi...
    wake_at: datetime | None = None      # ...hoặc tới giờ này
    done: str | None = None              # lý do đạt goal
    stop: str | None = None              # lý do dừng không đạt goal
    patch: dict[str, Any] = {}           # thay đổi vào state

class CaseSpec:
    kind: str
    state_model: type[BaseModel]
    goal: Callable[[State], str]
    triggers: tuple[Trigger, ...]
    graph: Graph
    stop: StopRules
    budget: Budget
    stop_if: Callable[[State, str], str | None] | None   # tin khách vừa nhắn → lý do dừng ("đừng nhắn nữa")
    verify: Callable[[State], str]                       # câu cho model: đọc lại đâu để biết đạt goal

class CaseRecord: ...     # bản ghi của bảng 2.3, không SQL

def blocked(spec, record, now) -> str | None     # lý do chặn cứng hoặc None
def apply(spec, record, decision, now) -> CaseRecord   # trạng thái mới sau một nút
def next_node(spec, record) -> str | None        # theo cạnh; cạnh quay lại tăng bộ đếm, quá trần → stop
def validate(spec) -> None                       # mọi cạnh quay lại phải có counter và trần; nút start tồn tại
```

Ba tool điều khiển (hình ở `agentcore.cases.tools`, lắp ở `agent_app`):

| Tool | Tham số | Nghĩa |
|---|---|---|
| `case_done` | `reason` | Đạt goal (model phải nói vì sao, kiểm được) |
| `case_wait_until` | `when` (ISO hoặc "khi khách trả lời"), `why` | Chờ, vòng tiếp tục ở lần thức sau với cùng goal và state |
| `case_need_human` | `why` | Dừng chờ nhân viên |

Model không gọi tool nào trong ba cái sau một TurnNode có `sends=True`: động cơ coi là `wait_for="customer"`. Sau
TurnNode có `sends=False`: theo cạnh mặc định. Tool chỉ ghi quyết định vào ca đang mở của `(channel,
conversation_id)` của lượt; không có ca mở thì trả lỗi "không có ca". Tool không đụng mạng, không đụng CRM.

### 2.3 Bảng (`agent_rt`, migration `0004_cases.sql`)

```sql
CREATE TABLE agent_rt.agent_case (
    id              bigserial PRIMARY KEY,
    tenant_id       text NOT NULL,
    agent           text NOT NULL,
    plugin          text NOT NULL,           -- plugin đăng ký spec
    kind            text NOT NULL,           -- CaseSpec.kind
    key             text NOT NULL,           -- chống trùng trong kind: vd conversation_id, hay appointment_id:starts_at
    channel         text NOT NULL,
    conversation_id text NOT NULL,
    user_id         text NOT NULL,
    session_id      text NOT NULL,
    goal            text NOT NULL,
    status          text NOT NULL,           -- open | waiting | needs_human | done | stopped
    node            text NOT NULL,           -- nút hiện tại
    state           jsonb NOT NULL,          -- CaseSpec.state_model
    wait_for        text,                    -- customer | clock | event | human
    wake_at         timestamptz,             -- waiting + clock
    deadline        timestamptz NOT NULL,    -- created_at + stop.max_age
    turns           integer NOT NULL DEFAULT 0,
    proactive_sent  integer NOT NULL DEFAULT 0,
    input_tokens    bigint  NOT NULL DEFAULT 0,
    output_tokens   bigint  NOT NULL DEFAULT 0,
    end_reason      text,                    -- done | stopped: vì sao
    version         integer NOT NULL DEFAULT 0,   -- khóa lạc quan
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    CHECK (status IN ('open','waiting','needs_human','done','stopped')),
    CHECK ((status IN ('done','stopped')) = (end_reason IS NOT NULL))
);
-- một ca sống cho mỗi (kind, key): sự kiện lặp, worker gửi lại không mở ca thứ hai
CREATE UNIQUE INDEX agent_case_live ON agent_rt.agent_case (tenant_id, agent, plugin, kind, key)
    WHERE status IN ('open','waiting','needs_human');
CREATE INDEX agent_case_wake ON agent_rt.agent_case (tenant_id, agent, wake_at)
    WHERE status = 'waiting' AND wake_at IS NOT NULL;
CREATE INDEX agent_case_chat ON agent_rt.agent_case (tenant_id, agent, channel, conversation_id)
    WHERE status IN ('open','waiting');

CREATE TABLE agent_rt.agent_case_event (      -- nhật ký quyết định: nhìn được vòng đã làm gì, vì sao
    case_id   bigint NOT NULL REFERENCES agent_rt.agent_case(id) ON DELETE CASCADE,
    seq       integer NOT NULL,
    at        timestamptz NOT NULL DEFAULT now(),
    kind      text NOT NULL,   -- opened | triggered | node | decision | sent | waiting | needs_human | resumed | done | stopped | blocked
    node      text,
    detail    jsonb NOT NULL DEFAULT '{}',    -- ≤ 2000 ký tự; lý do, tool nào, ingress id của lượt
    PRIMARY KEY (case_id, seq)
);

ALTER TABLE agent_rt.agent_settings
    ADD COLUMN cases_enabled boolean NOT NULL DEFAULT false,          -- công tắc tắt khẩn mọi ca
    ADD COLUMN proactive_per_person_per_day integer NOT NULL DEFAULT 2;
```

Lượt của ca nối với `agent_turn` qua `agent_ingress.external_id = 'case:<id>:<turns>'` (cùng cách
`followup:` hôm nay), nên token của ca cộng từ `agent_turn` như mọi lượt, không bảng mới.

### 2.4 Động cơ (`agent_app/cases/engine.py`)

Một job nền của lõi (không phải của plugin), chạy khi `agent serve`:

1. **Thức.** Ba nguồn, mỗi ca chỉ nghe nguồn trong `spec.triggers`:
   - đồng hồ: mỗi `tick_s` lấy ca `waiting` có `wake_at <= now` (giới hạn `per_pass`);
   - tin của khách: động cơ đăng ký `on_message` của host; tin trong `(channel, conversation_id)` có ca
     `waiting` với `wait_for='customer'` → đặt `wake_at = now`, chạy sau lượt trả lời khách (khóa phiên xếp hàng);
     trước đó gọi `spec.stop_if(state, text)`, có lý do thì dừng ca ngay, không chạy nút;
   - sự kiện: plugin gọi `ctx.cases.open(kind, key, state, chat)` hoặc `ctx.cases.wake(kind, key, patch)`.
2. **Chặn trước mỗi nút** (`agentcore.cases.blocked`): `cases_enabled` tắt, plugin tắt, quá `deadline`, quá
   `max_turns`, quá `max_proactive`, quá `budget.tokens`, bộ đếm quá trần, người này đã nhận đủ
   `proactive_per_person_per_day` (đếm `agent_case_event.kind='sent'` theo `user_id` từ đầu ngày địa phương, cộng
   mọi ca). Chặn thì `stopped` + lý do, ghi nhật ký.
3. **Chạy nút dưới khóa phiên** `SessionLocks.hold(session_id)`:
   - `CodeNode`: gọi `run(state, now)` của plugin; lỗi → ghi nhật ký, ca giữ nguyên, thử lại lần thức sau.
   - `TurnNode`: gửi `instruction` qua `Proactive.send_to` với `message_id='case:<id>:<turns>'` (chống trùng bằng
     unique `external_id` của `agent_ingress`); `turns += 1`; nếu khách nhận tin thì `proactive_sent += 1` và ghi
     `sent`. Quyết định lấy từ ba tool (ghi vào slot của ca trong lượt), không có thì mặc định như 2.2.
   - `HumanNode`: `needs_human`, ghi `why`.
4. **Áp dụng** `apply` + `next_node`; lưu với `version` (khóa lạc quan: hai tiến trình cùng chạy một ca thì một bên
   thua và bỏ qua). Mọi bước ghi một dòng `agent_case_event`.
5. **Admin** (`/v1/cases`): liệt kê theo trạng thái, xem nhật ký, `resume` (kèm ghi chú → nút kế), `close`. Giao
   diện nhân viên làm sau, phiên khác giữ frontend.

Plugin nhận qua `PluginContext`: `ctx.register_case(spec)` (một kind một plugin) và `ctx.cases` (`open`,
`wake`, `get`). Không có `ctx.register_case` nào thì động cơ không có gì để chạy: lõi không biết tên ca nào.

### 2.5 Ca đầu tiên: chăm sóc lại (plugin `follow_up`, thay `agent_app/follow_up.py`)

| Hôm nay (`agent_follow_up`) | Ca |
|---|---|
| hàng theo `(channel, conversation_id)` | `kind="follow_up"`, `key=conversation_id` |
| `state, reason, unanswered, reviewed_through, last_sent_at` | `state` (pydantic cùng tên trường) |
| `next_at`, `paused_until` | `waiting` + `wake_at` |
| `stopped` | `stopped` + `end_reason` |
| `review_pass` quét im lặng | job nhỏ của plugin: `quiet()` giữ nguyên, mỗi hội thoại im → `ctx.cases.open` |
| `_ask` (gọi model phán đoán) | `CodeNode("judge")`: plugin gọi `ctx.model` với `SYSTEM_PROMPT` hôm nay, trả `Decision` |
| `_send` | `TurnNode("write", instruction_for, sends=True)` |
| `may_send` | `StopRules(max_proactive=2, counters={"unanswered": 2}, max_age=14 ngày)` + `blocked` |
| `asks_to_stop` | `spec.stop_if` |
| `follow_up_enabled`, `follow_up_channels` ở `agent_settings` | `user_config` của plugin |
| `FollowUpPolicy` hằng trong code | `user_config` (giờ nhắn, khoảng cách, số lần) |

Đồ thị: `judge` → (hesitant, call_back, soft_decline) `wait clock` → `write` → `wait customer` → `judge` (cạnh quay
lại, `counter="unanswered"`, khách trả lời thì nút judge đặt lại 0); `judge` → done khi `done`; stop khi
`hard_decline`, `negative`. Migration chuyển dữ liệu: hàng có `next_at` → ca `waiting`; `stopped` → ca
`stopped`; còn lại → `done`. Bỏ bảng cũ và hai cột cài đặt; bỏ `follow_up_*` khỏi gateway và `app_runtime`.

### 2.6 Nhắc lịch lên cùng động cơ (sau, plugin `crm`)

`kind="reminder"`, `key=f"{appointment_id}:{starts_at}"`, mở khi sự kiện `appointment.changed` tới (hoặc đối
soát), state = `Visit` + người; mỗi mốc là một `CodeNode` gọi `decide()` hôm nay rồi `TurnNode` gửi; `claim_mark`
thay bằng unique `(kind, key)` + `turns`. Bảy lý do bỏ giữ nguyên trong `decide`. Chỉ chuyển khi 2.5 chạy ổn.

### 2.7 Luật ranh giới và test

- Ba tool điều khiển là tool mới trong profile `clinic` → **L7: chủ duyệt bằng văn bản** trước khi lắp; T9 cập
  nhật danh sách. Tool không ra mạng, chỉ ghi `agent_rt`. L1–L6 không đổi.
- Test thuần (`packages/agent-core/tests/test_cases.py`): `validate` từ chối cạnh quay lại không có counter;
  `blocked` cho từng luật; `apply` cho từng loại `Decision`; `next_node` tăng bộ đếm và dừng khi quá trần.
- Test động cơ với store trong RAM: một trigger chạy một nút; chạy hai lần cùng `message_id` gửi một lần; khách
  nhắn "đừng nhắn nữa" dừng ca trước khi chạy nút; `cases_enabled=false` chặn mọi ca; trần theo người cộng hai ca.
- Test T9 cấu trúc import (2.1).
- Sau khi làm: cập nhật ERD `agent_rt` và sơ đồ vòng chăm sóc lại trong `.archify/` (luật `diagram-after-task`).

---

## 3. Thứ tự làm (mỗi bước một commit, chờ "go")

1. Ngân sách theo phiên và ngày trước `run_turn` (đếm từ `agent_turn`, ngưỡng ở `agent_settings`, một test).
2. Hợp đồng `JudgeService`, `EmbeddingService` ra package trung lập; test T9 giữ chiều import.
3. `agentcore.cases` thuần + test (2.2).
4. Migration `0004_cases`, store, `CaseEngine`, ba tool điều khiển (cần chủ duyệt L7), route admin (2.3, 2.4).
5. Plugin `follow_up` trên động cơ, migration chuyển dữ liệu, bỏ `agent_app/follow_up.py` (2.5).
6. Nhắc lịch của `crm` lên động cơ (2.6).
7. Ngưỡng `run_turn` và nén ra cài đặt.

**Để mở, chủ quyết sau:** `Edge.when` và `CodeNode.run` đang là hàm Python khai báo trong danh sách; đổi thành biểu
thức dữ liệu (TOML, JSON) là việc graph engineering của chủ, động cơ không cần đổi. Giao diện nhân viên cho
`needs_human`. Ca gọi ca khác (subagent thật) chưa có.
