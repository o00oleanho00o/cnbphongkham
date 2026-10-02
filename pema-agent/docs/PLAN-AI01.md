# PLAN-AI01 — Pema Agent: bản phái sinh zalo-agent bằng Python + CRM phòng khám

Trạng thái: kế hoạch, chưa có code. Nhánh: `feat/ai-agent-backend`. Phiên bản 2 (2026-10-01), thay thế bản 1 "chỉ lấy phần kênh".

**Mọi thứ mới nằm trong một thư mục duy nhất `pema-agent/`.** Code cũ (`prototype/`, `pema-kmp/`, `finance_server.py`, `docs/` PB01/PB02) chỉ được đọc. Ngoại lệ: một dòng trỏ trong `README.md` gốc và một checkpoint trong `SECTION_PROGRESS.md`, do gói F làm sau cùng.

Cách chạy: sau một lệnh "go" duy nhất, làm **toàn bộ** các gói theo mục 6, không dừng chờ duyệt giữa các stage. Người nhận một báo cáo tổng hợp cuối và danh sách việc mở.

Tài liệu này là brief chung cho người và subagent. Mọi subagent đọc file này, `AGENT.md`, và `docs/ARCH-PB01.md` trước khi làm.

---

## 1. Mục tiêu

Hai việc trong một codebase:

1. **Dịch toàn bộ `vuhai2002/zalo-agent` (TypeScript) sang Python** làm engine agent: kênh Zalo (Bot API + tài khoản cá nhân), vòng lặp agent, persona, 15 tool, memory, knowledge base, scheduler, MCP client, kế toán token. Giữ hành vi và bộ test tương đương.
2. **Thêm CRM phòng khám** (hồ sơ, lịch, mốc chăm sóc, Inbox, hàng đợi duyệt) và một **FE Next.js duy nhất** cho cả CRM lẫn cấu hình AI, để nhân viên không phải dùng nhiều app.

Zalo là kênh ra khách. Giai đoạn này chỉ CSKH bằng chữ với bệnh nhân; tool ảnh/video/tài liệu vẫn được port nhưng **tắt trong hồ sơ `patient_channel`**.

## 2. Nguyên tắc

1. **Trung thành với nguồn khi dịch.** Mỗi module Python ánh xạ 1-1 với file TS gốc (ghi `# ported from: src/<path>.ts` ở đầu file). Giữ tên khái niệm, hằng số, ngưỡng và lý do đã ghi trong comment gốc. Test TS dịch sang pytest cùng tên.
2. **An toàn cho bệnh nhân bằng hồ sơ chính sách, không bằng xóa tính năng.** Hai hồ sơ: `staff_assistant` (giống zalo-agent gốc) và `patient_channel` (xem mục 5). Hồ sơ gắn với từng agent/account trong cấu hình.
3. **Agent đi qua cùng lớp action với UI.** Tool CRM của agent (`patient.get_care_context`, `appointment.book`, `review_item.create`, ...) là chính hàm REST route gọi.
4. **Dữ liệu bệnh nhân không vào vector store, không ra khỏi hạ tầng.** Che PII trước mọi lời gọi LLM trong `patient_channel`. AI engine chỉ đọc `clinic.*` qua actions có phân quyền.
5. **Tuân `AGENT.md`:** dữ liệu trong repo hư cấu; AI draft kèm nguồn, bác sĩ duyệt; không chẩn đoán tự động; sinh nhật không gửi tự động; `marketingOptOut` chặn marketing.
6. **Giữ thông báo bản quyền.** Bản phái sinh theo MIT: `pema-agent/THIRD_PARTY_NOTICES.md` ghi bản quyền zalo-agent (và zca-js). Không hạn chế gì thêm.

## 3. Kiến trúc

```
Khách (Zalo) ─► Bot API ──webhook/polling──► ┌──────────── BE Python (FastAPI) ────────────┐
                Tài khoản cá nhân ──► Node    │ channels/   zalo_bot · zalo_personal (ChannelPort)│
                bridge zca-js ──HTTP──────────►│ middleware/ allowlist · rate-limiter · batcher   │
                                              │ agent/      loop · persona · tools · guards      │
Nhân viên ─► Next.js FE ──► BE API ──────────►│ conversation/ history · memory · summary · usage │
                                              │ knowledge/  ingest · chunk · hybrid search       │
                                              │ scheduler/  jobs · caps · delivery · recovery    │
                                              │ mcp/        HTTP client · per-agent policy       │
                                              │ clinic/     domain · actions · crm rules · RBAC   │
                                              │ policy/     staff_assistant · patient_channel    │
                                              └───────┬──────────────┬───────────────────────────┘
                                        Postgres clinic.* + agent.*   Redis (queue, locks)
                                        pgvector + FTS                 Object storage (file, ảnh)
                                                      │
                                        LLM: OpenAI-compatible (Ollama/llama-server trên PC
                                        RTX 3060, Qwen3-8B + bge-m3) · Anthropic · Gemini
```

- **Một repo, nhiều tiến trình:** `api` (1 nhân CPU), `worker` (agent turns + scheduler, chạy trên PC GPU hoặc server), `zalo-personal-bridge` (Node, tuỳ chọn).
- **Postgres thay SQLite** của bản gốc. Hai schema: `clinic.*` (CRM) và `agent.*` (accounts, agents, threads, history, memory, kb, jobs, usage, mcp). Role `agent_worker` đọc `clinic.*` chỉ qua view/function được cấp, không đọc bảng thô.
- **Vercel AI SDK → vòng lặp tool tự viết** trên `openai` SDK (OpenAI-compatible) + adapter Anthropic/Gemini, giữ nguyên ngữ nghĩa step/`tool-loop-guard`/`maxRetries` của bản gốc. Không dùng LangGraph cho vòng lặp này để ánh xạ 1-1 dễ hơn.
- **FTS5 + BM25 + RRF → Postgres FTS + pgvector + RRF.** Thêm vector là phần mở rộng duy nhất so với gốc.
- **node:sqlite đồng bộ → SQLAlchemy async.** Những bất biến dựa trên "một tiến trình đồng bộ" (claim job, đếm trần) chuyển sang SQL nguyên tử + khóa Redis.

## 4. Cấu trúc thư mục

```
pema-agent/
  README.md · Makefile · THIRD_PARTY_NOTICES.md
  backend/
    pyproject.toml                uv workspace, Python 3.12+ (3.14 nếu thư viện đủ)
    packages/contracts/           pydantic DTO dùng chung; ChannelPort; job payload
    apps/api/pema/
      channels/zalo_bot/ zalo_personal/   ← src/zalo-bot, src/zalo
      middleware/                          ← src/middleware
      agent/                               ← src/agent (loop, persona, tools/*, guards, providers)
      conversation/                        ← src/conversation (history, memory, summary, usage, threads)
      knowledge/                           ← src/knowledge (+ pgvector)
      scheduler/                           ← src/scheduler
      mcp/                                 ← src/mcp
      documents/ images/ video/            ← src/documents, src/images, src/video
      config/                              ← src/config (account/agent store, 70 tham số tuning)
      clinic/   domain/ actions/ crm_rules/ rbac/ audit/   ← mới, port từ crm-automation.js
      policy/   profiles.py (staff_assistant, patient_channel), redflags.py, pii.py  ← mới
      api/      routers mỏng → actions; webhook Zalo; admin
      workers/  agent turn worker, scheduler loop
      alembic/  clinic.* và agent.*
    bridges/zalo-personal/        Node 22 + zca-js + Hono (tuỳ chọn, cờ tắt)
  frontend/                       Next.js App Router, TS, Tailwind, openapi-typescript
  infra/                          docker-compose, .env.example, Ubuntu + Ollama/llama-server, Tailscale
  kb-samples/                     tài liệu da liễu HƯ CẤU
  evals/                          dịch 17 kịch bản gốc + bộ CSKH da liễu
  docs/                           PLAN-AI01, SCOPE/SPEC/MODULEMAP/ARCH-AI01, PORT-MAP.md (bảng file TS → Python)
```

## 5. Hồ sơ chính sách

| | `staff_assistant` | `patient_channel` |
|---|---|---|
| Tin ra khách | Gửi thẳng | **Vào `review_item`, người duyệt rồi gửi** |
| Job `kind: agent` theo lịch | Cho phép | Chỉ `kind: message` từ template; agent chỉ soạn nháp |
| `save_memory` | Cho phép | Tắt với nội dung từ bệnh nhân; chỉ bác sĩ/CSKH ghi |
| Tool ảnh/video/tài liệu/web | Theo cấu hình | Tắt; khách gửi ảnh → gắn cờ Inbox, chuyển người |
| Cờ đỏ (chảy máu, sốt, mưng mủ, khó thở, có dấu/không dấu) | Không áp | **Chuyển bác sĩ trước khi gọi LLM** |
| Che PII trước LLM | Tuỳ chọn | Bắt buộc |
| Trần tin chủ động/ngày | Theo account | Theo bệnh nhân + account; `marketingOptOut`; sinh nhật không tự gửi |
| Xác minh danh tính `zalo_uid` ↔ hồ sơ | Không cần | Bắt buộc trước khi nhắc tên/lịch/thuốc |

## 6. Gói việc cho subagent

Mỗi gói: một subagent `pema-builder` (Sonnet 5.5, effort cao), worktree riêng, chỉ chạm thư mục của mình trong `pema-agent/` + test. Nguồn tham chiếu: bản clone zalo-agent **ngoài repo** tại đường dẫn ghi trong `docs/PORT-MAP.md` (gói A tạo).

| Gói | Phạm vi | Nghiệm thu |
|---|---|---|
| **A. Contracts, skeleton, PORT-MAP** (một mình, trước) | Khung thư mục; `pyproject`; lint/pyright/ruff/import-linter; OpenAPI skeleton (CRM + admin agent); DDL `clinic.*`/`agent.*` + role; `ChannelPort`; `THIRD_PARTY_NOTICES.md`; **`PORT-MAP.md`** liệt kê mọi file TS → module Python + gói phụ trách; clone zalo-agent vào vị trí cố định ngoài repo | OpenAPI sinh được; DDL chạy trên Postgres sạch; pytest rỗng pass; FE sinh types; PORT-MAP phủ 100% `src/` |
| **B1. Clinic core** | auth JWT, RBAC theo ma trận ARCH-PB01, audit, RLS; actions + routes patients/360, appointments, conversations, review_items, consent | pytest hành vi chính; mọi mutation có audit |
| **B2. CRM rules → scheduler** | Port 10 rule `crm-automation.js`/`crm-data.js` thành policy engine sinh job vào `scheduler/` của gói S; `marketingOptOut`; sinh nhật không tự gửi | **Test tương đương** với bản JS (clock 2026-09-20, case P025–P032) |
| **C1. Zalo Bot API** | Dịch `src/zalo-bot` + `src/middleware`; webhook + polling; chống trùng update_id | Dịch test gốc; chạy với bot thử nghiệm |
| **C2. Zalo personal** | Node bridge zca-js + dịch `src/zalo` (account-manager, split/sanitize/markdown, send-in-parts); cờ tắt; hạn mức; kill switch | Dịch test gốc; README nêu rủi ro khóa tài khoản |
| **D1. Agent engine** | Dịch `src/agent`: loop, persona, provider (OpenAI-compatible/Anthropic/Gemini), tool registry, tool-loop-guard, prompt-leak-markers, trace, usage/token accounting, ngân sách context theo token | Dịch test gốc; LLM giả cho test; chạy thật với Ollama |
| **D2. Conversation & memory** | Dịch `src/conversation`: history, rolling summary, `save_memory`, image cache, threads, usage store | Dịch test gốc |
| **D3. Knowledge** | Dịch `src/knowledge` (parse an toàn docx/xlsx/pdf/txt/md, trần zip bomb, worker timeout) + pgvector/bge-m3 + Postgres FTS + RRF | Dịch test gốc; test hybrid |
| **D4. Tools** | Dịch `src/documents`, `src/images`, `src/video`, web_search/web_fetch (SSRF guard), send_file, reactions, tag_member, get_group_info, get_datetime, schedule_task, kb_search; cờ `runs_in_scheduled_turn`, giới hạn theo kênh | Dịch test gốc |
| **D5. MCP client** | Dịch `src/mcp`: HTTP transport, per-agent default-deny, fingerprint drift | Dịch test gốc |
| **S. Scheduler** | Dịch `src/scheduler` đầy đủ (parser, next-run, loop, caps nguyên tử, delivery attempts, recovery, silent sentinel, trial run) sang Postgres/Redis | Dịch test gốc, đặc biệt bất biến "chưa gửi thì chưa chạy" |
| **P. Policy** | `profiles.py`, `redflags.py`, `pii.py` (SĐT/CCCD/email VN, tên→mã), gắn vào agent loop, scheduler, channel; luồng xác minh `zalo_uid` | pytest; case cờ đỏ không gọi LLM |
| **E. Next.js FE** | Vận hành: Việc hôm nay, Inbox, Hàng đợi duyệt, Patient 360. Quản trị AI (dịch tính năng dashboard gốc): accounts/QR, agents/persona, model, tools, KB sources, schedules, MCP servers, usage/token, logs. Mobile-first; brand token | build/lint pass; chạy với BE mock; kiểm 5 viewport |
| **F. Infra & docs** | docker-compose; `.env.example`; hướng dẫn Ubuntu + Ollama/llama-server; Tailscale; SCOPE/SPEC/MODULEMAP/ARCH-AI01; README; dòng trỏ ở README gốc + SECTION_PROGRESS | `docker compose up` lên được; docs khớp hành vi thật |
| **M. Care agent per khách (multi-agent)** (sau D1, S, P, B1; trước G) | Xem **`PLAN-AI01-M.md`**: agent chăm sóc riêng 1-1 cho từng khách, chủ động theo sự kiện; bậc tự chủ L0–L2; máy trạng thái AUTO→HANDOFF_ROUTING→STAFF; skill `handoff` tự cảm nhận; tự chọn/đổi nhân viên theo kỹ năng, SLA, kết thúc ở số trực 24/24; Scheduler/Knowledge/Reviewer agent | Theo §13 của PLAN-AI01-M (M1–M6) |
| **G. Tích hợp & review** (sau cùng) | Gộp worktree; chạy toàn bộ test; vòng khép kín cả hai hồ sơ; review bảo mật (PII, grant DB, token, SSRF); đối chiếu PORT-MAP không sót file | Báo cáo + fix nhỏ; việc mở |

Thứ tự: **A** → (B1, B2, C1, C2, D1, D2, D3, D4, D5, S, P, E song song; F bắt đầu phần hạ tầng) → **M** (cần D1, S, P, B1 xong) → **F** docs → **G**. Phụ thuộc mềm: B2 và P cần giao diện của S và D1, lấy từ contracts của A.

## 7. Quy ước cho subagent

- **Chỉ tạo/sửa file trong `pema-agent/`.** Code cũ ngoài đó chỉ đọc.
- Đọc `AGENT.md`, `pema-agent/docs/PLAN-AI01.md`, `docs/ARCH-PB01.md`, và `pema-agent/docs/PORT-MAP.md` trước.
- **Dịch, không sáng tác lại.** Giữ cấu trúc, tên, ngưỡng, comment lý do của bản gốc; mỗi file Python ghi nguồn TS. Khác biệt bắt buộc (SQLite→Postgres, Vercel AI SDK→openai SDK, đồng bộ→async) ghi trong docstring đầu file.
- Dữ liệu test, fixture, KB mẫu **hư cấu**. Không SĐT thật, tên thật, không chép nội dung ghi âm khách hàng.
- Không commit `.env`, token, DB. Mỗi service có `.env.example`.
- Không đọc/sửa `flutter-template/`. Không grep đệ quy toàn repo; scope vào thư mục mình và bản clone tham chiếu.
- Python: uv, ruff, pyright strict, pytest, SQLAlchemy async. TS: pnpm, eslint, prettier. Không `print`/`console.log` debug; logger không log PII.
- Báo cáo cuối ≤ 30 dòng: làm gì, test chạy gì và kết quả thật, giả định, việc mở. Không dán log dài.
- Không tự mở rộng phạm vi. Quyết định sản phẩm ghi vào "việc mở".

## 8. Quyết định đã chốt (2026-10-01)

- Chưa có Zalo OA/ZNS → chỉ Bot API và tài khoản cá nhân; `oa_api.py` là stub.
- PC chạy **Ubuntu cài hẳn**; LLM qua Ollama, sau là llama-server. **Tạm thay bằng API bên thứ ba từ 2026-10-02**, xem dưới.
- Vitech/MISA không đụng trong AI01.
- Giữ cả Zalo và Patient app (web + KMP).
- Bác sĩ trong đội duyệt template/KB/nháp. Pháp lý (Nghị định 13/2023) thuộc trách nhiệm chủ phòng khám; code giữ che PII, consent, audit, RLS.
- Chưa quyết: vị trí server (phòng khám hay cloud VN), sao lưu, UPS.

**Cập nhật 2026-10-02 (chủ dự án yêu cầu): tạm dùng API LLM của bên thứ ba, như zalo-agent.** Cấu hình mặc định
trỏ tới một provider bên ngoài (`openai-compatible` qua OpenRouter/OpenAI/DeepSeek/9Router, hoặc `anthropic`,
`google`), nhập trên màn Quản trị > Model. LLM local (Ollama, `pema-chat`, `bge-m3`) **tạm tắt**: service `ollama`
trong compose, target `up-ollama`, khối Ollama của `.env.example` và preset Ollama trên FE được chú thích với nhãn
`TẠM TẮT LLM LOCAL (2026-10-02)`; embedding mặc định tắt nên kho kiến thức chỉ tìm theo từ khóa (đúng như bản gốc).
Code adapter không đổi. Hệ quả: nội dung hội thoại rời hạ tầng phòng khám. `patient_channel` vẫn che PII trước mọi
lời gọi LLM; `staff_assistant` thì không bắt buộc che, nên nhân viên không được dán dữ liệu bệnh nhân vào kênh đó.
Cần hợp đồng xử lý dữ liệu với nhà cung cấp theo Nghị định 13/2023 trước khi dùng dữ liệu thật.
