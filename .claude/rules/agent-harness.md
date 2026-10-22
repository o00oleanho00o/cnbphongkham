# Triết lý agent và harness — luật bất biến

Áp cho mọi thay đổi trong `pema-agent/backend` (lõi `packages/agent-core`, app `apps/agent`, plugin `apps/agent/plugins`),
kể cả do subagent làm. Chủ hệ thống chốt (2026-10-22); thiết kế đầy đủ: `pema-agent/docs/DESIGN-case-loop.md`, kế hoạch và
các quyết định đã làm: `pema-agent/docs/PLAN-case-loop.md`. Luật ranh giới agent ↔ CRM (L1–L7) ở
`agent-crm-boundary.md` vẫn áp song song.

## Công thức

**Agent = Model + Harness.** **Harness = Context + Tool interfaces + Constraints + Verification + Correction.**
**Agent ↔ Environment** (khách, CRM, đồng hồ). Model là một nút trong đồ thị do harness chạy, không phải bộ não ra lệnh
cho harness. Mọi tính năng (RAG, CRM, nhắc lịch, chăm sóc lại…) là **plugin**; harness không biết plugin nào tồn tại.

## Luật

- **H1. Ba lớp, import một chiều.** Hình (`agentcore.cases`, thuần: pydantic và stdlib, không DB, không model, không
  plugin) ← Chạy (`agent_app/cases`, động cơ, store) ← Nội dung (plugin: khai báo ca bằng `ctx.register_case`, mở hay
  đánh thức ca bằng `ctx.cases`). Lõi và động cơ không bao giờ import plugin, không bao giờ có `if kind == "..."`,
  không đọc bảng của plugin. Plugin không bao giờ sửa con trỏ, trạng thái hay bản ghi ca của động cơ, chỉ đi qua
  `ctx.cases`.
- **H2. Vòng và đồ thị là dữ liệu.** Trigger, điều kiện dừng, state, cạnh, bộ đếm, trần là dữ liệu khai báo trong
  `CaseSpec`, không viết cứng trong vòng lặp. Chủ sẽ tự làm graph engineering sau: không chốt cứng thứ gì ngăn việc đổi
  `Edge.when`, `CodeNode.run` thành biểu thức dữ liệu.
- **H3. Mọi vòng phải dừng được.** Cạnh quay lui (kể cả cạnh lỗi) phải mang bộ đếm có trần trong `StopRules.counters`;
  ca có `max_turns`, `max_proactive`, `max_age`; động cơ có `max_nodes_per_pass`. `CaseSpec` sai luật thì không dựng
  được: giữ các kiểm đó trong `_check`, không nới.
- **H4. Code quyết cái gì kiểm được bằng dữ liệu; model chỉ làm phần cần ngôn ngữ.** Gửi hay không, lúc nào, cho ai,
  bao nhiêu, đúng giờ ngày nào: code (`CodeNode`, `decide()`, `blocked`). Model (`TurnNode`): viết câu chữ, đọc ngữ
  cảnh cuộc chat mà code không đọc được, và chỉ có quyền **từ chối** (`SKIP`) hoặc điều khiển ca qua tool điều khiển
  (`case_done`, `case_wait_until`) khi đúng lượt của ca. Giờ, ngày, mã, số tiền do code viết vào lời dặn; model không
  được đổi.
- **H5. Kiểm ngay trước khi làm.** Một bước có tác động ra ngoài (nhắn khách) phải có bước kiểm bằng code chạy liền
  trước nó trong cùng lượt quét, kể cả lần thử lại sau lỗi: nút lỗi phải đi theo cạnh lỗi (`Edge(on="error")`) về
  bước kiểm, không thử lại thẳng ở nút gửi. Ca đang đợi được sự kiện đánh thức thì chạy bước kiểm trước.
- **H6. Ràng buộc chung nằm ở harness, plugin hỏi chứ không đếm riêng.** Trần tin mỗi người mỗi ngày tính chung cho
  mọi ca (động cơ đếm, plugin hỏi qua `ctx.cases.room_today`); trần token mỗi phiên và mỗi agent mỗi ngày
  (`TokenBudget`, kiểm trước `run_turn`); công tắc khẩn `cases_enabled`. Không plugin nào tự đếm một trần trùng với trần
  của harness theo cách khác, vì hai cách đếm lệch nhau sẽ làm ca kẹt ở nút gửi.
- **H7. Trạng thái bền nằm trong DB, không trong RAM.** Ca, quyết định của tool điều khiển (`agent_case.pending`, theo
  mã lượt `case:<id>:<lượt>`), nhật ký (`agent_case_event`). Khởi động lại hay tiến trình khác vớt lượt thì không mất
  gì, không gửi hai lần (mã tin là khóa chống trùng của hàng đợi).
- **H8. Lượt của ca tách khỏi lượt của khách.** Tin chủ động (ca, nhắc lịch, chăm sóc lại) không bao giờ gộp lượt
  với tin khách; lượt của khách không điều khiển được ca. Động cơ không giữ khóa phiên (lượt giữ).
- **H9. Prompt và cache không đổi khi không cần.** Tool điều khiển chỉ có trong registry khi một plugin đang bật khai
  báo ca. Thêm gì vào prompt hay danh sách tool là đổi vân tay cache: cân nhắc và ghi lý do.
- **H10. Khái niệm mới ở lõi phải chung.** Chỉ thêm vào `agentcore.cases` hay động cơ một khái niệm dùng được cho mọi
  ca (cạnh lỗi, `room_today`…), không phải một ngoại lệ cho một plugin. Một nhu cầu riêng của plugin thì giải
  ở plugin (nút mã, state, cách đặt khóa ca).
- **H11. Plan trước, code sau.** Thay đổi lớn (khái niệm lõi, động cơ, đổi hành vi cho khách) viết vào kế hoạch, chờ chủ
  nói "go". Tool mới cho profile `clinic` là đổi L7: chủ duyệt bằng văn bản, sửa danh sách T9.

## Khi viết một ca mới (checklist)

1. State là `BaseModel`; khóa ca (`key`) xác định "một lần" theo nghĩa nghiệp vụ (ví dụ một mốc của một lịch).
2. Đồ thị: nút kiểm (`CodeNode`) trước mỗi nút gửi (`TurnNode`); cạnh lỗi từ nút gửi về nút kiểm, có bộ đếm.
3. Mọi lý do bỏ qua là hàm thuần có test riêng; nút kiểm đọc lại dữ liệu mới nhất, không tin state cũ.
4. `StopRules`, `Budget` đặt chặt nhất có thể; chống trùng sau khi ca đã đóng phải có chốt riêng (động cơ chỉ chống
   trùng ca còn sống).
5. Test trên động cơ thật với `InMemoryCaseStore`: gửi đúng một lần, chờ đúng giờ, sự kiện kết thúc ca, gửi lỗi rồi
   kiểm lại, trần mỗi ngày, công tắc tắt.

## Test giữ luật

| Test | Luật | Ở đâu |
|---|---|---|
| harness không import plugin | H1 | `apps/agent/tests/test_tool_allowlist.py::test_the_harness_never_imports_what_plugs_into_it` |
| spec sai luật bị từ chối (cạnh lùi không bộ đếm, cạnh lỗi có điều kiện…) | H2, H3 | `packages/agent-core/tests/test_cases.py` |
| tool điều khiển chỉ khi có plugin khai báo ca; lượt khách không điều khiển ca; quyết định sống qua khởi động lại; `room_today` khớp `blocked` | H4, H6, H7, H8, H9 | `apps/agent/tests/test_cases_engine.py` |
| tin chủ động không gộp lượt | H8 | `apps/agent/tests/test_queue_modes.py` |
| trần token | H6 | `apps/agent/tests/test_token_budget.py` |
| ca nhắc lịch: kiểm trước gửi, gửi lỗi quay về kiểm, sự kiện kết thúc ca | H4, H5 | `apps/agent/tests/crm/test_crm_reminders.py` |
