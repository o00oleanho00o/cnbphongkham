# PLAN-AI01-M — Gói M: Agent chăm sóc riêng cho từng khách (multi-agent)

Trạng thái: kế hoạch đã chốt với chủ dự án (2026-10-02). Bổ sung cho `PLAN-AI01.md`; chạy **sau** các gói D1 (agent engine), S (scheduler), P (policy), B1 (clinic core). Mọi quy ước ở `PLAN-AI01.md` §2 và §7 áp dụng nguyên vẹn.

---

## 1. Ý tưởng

Mỗi khách (bệnh nhân) được **ghép 1-1 với một agent chăm sóc riêng** (`care_agent`). Agent này hoạt động như một nhân viên CSKH phụ trách đúng khách đó: **chủ động** theo dõi hành trình điều trị, tự quyết định trả lời hay chuyển người, tự chọn đúng nhân viên và tự đổi người khi không được hỗ trợ. Nhân viên chuyển từ vai "điều khiển" sang vai "giám sát", chỉ còn hai nút: **Nhận/Từ chối** yêu cầu chuyển giao và **Trả lại cho agent**.

Không làm trong gói M: agent nói chuyện với khách theo nhóm nhiều agent; agent tự tạo agent; worker gọi worker (độ sâu giao việc = 1).

## 2. Mô hình kỹ thuật: actor, không phải tiến trình riêng

- `care_agent` là **bản ghi + bộ nhớ trong DB**, không phải LLM chạy riêng. Một pool worker chạy "lượt" cho khách nào đang có sự kiện. Cùng engine vòng lặp của gói D1, cùng scheduler của gói S.
- Mỗi lượt: nạp ngữ cảnh khách (qua `actions/` có RBAC, đã che PII) → chạy skill `handoff` (mục 6) → hành động trong tập được phép → ghi log → ngủ.
- Một GPU 12 GB nên lượt chạy **tuần tự** theo ưu tiên: khách đang nhắn > sự kiện đến hạn > tick hằng ngày. Tick chạy theo lô lúc 6h, gửi trong khung giờ cho phép (mặc định 8h–20h, cấu hình).
- Phần lớn tick là **quy tắc không cần LLM**; chỉ gọi LLM khi có việc cần soạn.

## 3. Sự kiện đánh thức agent (ai cũng khởi xướng được)

| Người khởi xướng | Sự kiện | Việc agent thường làm |
|---|---|---|
| Khách | Nhắn Zalo | Phân loại, trả lời theo mức tự chủ hoặc chuyển người |
| Hệ thống (gói S + B2) | Hoàn tất buổi điều trị; mốc D+1/3/7; đến hạn/quá hạn tái khám; vắng hẹn; im lặng 90/180 ngày; sinh nhật | Lên kế hoạch, nhắc, hỏi thăm, đề xuất lịch |
| Hệ thống | Tick hằng ngày 6h | Rà toàn bộ trạng thái khách, tìm việc bỏ sót |
| Nhân viên | Gõ lệnh cho agent của khách trên dashboard | "Gửi lại hướng dẫn sau laser", "Tuần sau mới nhắc", "Để tôi xử lý" |
| Bác sĩ | Sửa/duyệt nháp của agent này | Ghi nhớ cách sửa cho khách này, cộng/trừ điểm tin cậy |

Cả ba nguồn đi vào **cùng một pipeline** (`HarnessProcessor`, gói D1), chỉ khác trường `initiator`. Luật, log, trần tin áp dụng như nhau.

## 4. Mức tự chủ theo loại hành động (cấp riêng cho từng care_agent)

| Mức | Agent được làm không cần duyệt | Cách lên mức |
|---|---|---|
| **L0** | Không gì; mọi thứ là nháp | Mặc định cho khách mới và sau khi bị hạ |
| **L1** | Gửi tin **từ template đã bác sĩ duyệt** (nhắc lịch, nhắc thuốc, hướng dẫn chăm sóc chuẩn); xác nhận lịch khách chọn | Phòng khám bật template đó |
| **L2** | Trả lời câu hỏi thường gặp **từ KB** khi có trích nguồn, độ tin cậy ≥ ngưỡng, không cờ đỏ | Sau N nháp cùng loại của agent này được duyệt **không sửa** (N do bác sĩ chốt) |
| **Luôn cần người** | Mọi phán đoán y khoa; đổi thuốc; triệu chứng bất thường; cờ đỏ (chuyển bác sĩ ngay, không gọi LLM) | Không bao giờ tự động |

Hạ mức: bác sĩ/quản lý hạ bất cứ lúc nào; một lần bị sửa nghiêm trọng → tự về L0. Khi trả hội thoại về AUTO, nhân viên có thể **hạ mức có thời hạn** (ví dụ L0 trong 7 ngày rồi tự về mức cũ). Mọi thay đổi mức được log.

## 5. Máy trạng thái kiểm soát hội thoại (per khách)

```
AUTO ──agent tự cảm nhận cần người──► HANDOFF_ROUTING ──nhân viên Nhận──► STAFF
 ▲                                      │  ▲                                 │
 │                                      │  └── Từ chối / quá SLA → ứng viên kế │
 │                                      └── hết chuỗi → số trực 24/24 (luôn có) │
 └──────────── nhân viên "Trả lại cho agent" (kèm ghi chú, tùy chọn hạ mức) ◄──┘
```

| Trạng thái | Agent | Nhân viên |
|---|---|---|
| **AUTO** | Trả lời/chủ động theo L0–L2 | Giám sát dòng thời gian, duyệt nháp |
| **HANDOFF_ROUTING** | Im lặng với khách; gửi **một** câu giữ chỗ template; tóm tắt ngữ cảnh cho ứng viên; chạy vòng định tuyến (mục 7) | Nhận thông báo kèm tóm tắt + lý do; bấm Nhận hoặc Từ chối (lý do, gợi ý người khác) |
| **STAFF** | **Không tự phản ứng**: không trả lời, **không gửi nhắc theo lịch** (xem mục 8); quan sát, gợi ý nháp cho nhân viên (không gửi), học cách nhân viên trả lời | Nhắn trực tiếp qua Inbox; thấy nhắc "đã tạm dừng", gửi tay nếu muốn |
| Về **AUTO** | Đọc ghi chú, cập nhật ngữ cảnh, đối soát nhắc tạm dừng (mục 8), tiếp tục | Bấm "Trả lại cho agent", chọn mức tự chủ (giữ hoặc hạ có thời hạn) |

Quy tắc cứng: **chỉ nhân viên mới trả về AUTO**. Không hết hạn tự động (tùy chọn "tự trả về sau N giờ im lặng" có nhưng mặc định tắt). Port và mở rộng cờ `bot_enabled` theo thread của zalo-agent thành máy trạng thái này.

## 6. Skill `handoff`: agent tự cảm nhận khi nào cần người

Không có nút "gặp người" trong luồng. Trước **mỗi** lần định trả lời, agent chạy skill `handoff` (instruction + bộ phân loại), cân các tín hiệu:

| Nhóm tín hiệu | Ví dụ |
|---|---|
| Độ sâu câu hỏi | D1 hành chính · D2 chăm sóc chuẩn · D3 triệu chứng nhẹ trong dự kiến · D4 phán đoán y khoa · D5 cờ đỏ |
| Độ tin cậy của chính nó | Không có nguồn KB; mâu thuẫn; dưới ngưỡng |
| Trạng thái khách | VIP; tiền sử phức tạp; từng khiếu nại; chưa xác minh danh tính (chỉ D1) |
| Cảm xúc, diễn biến | Bực; lặp câu hỏi; câu trả lời trước không được chấp nhận; khách nói muốn gặp người (một tín hiệu, không phải lệnh) |
| Bối cảnh | Ngoài giờ; trong 48h sau thủ thuật; đang có việc chờ bác sĩ |
| Giới hạn quyền | Việc cần làm vượt mức tự chủ hiện tại |

Đầu ra có cấu trúc: `{action: answer|handoff, reason, depth: D1..D5, confidence, required_skill, urgency}`.

Mặc định theo độ sâu (bác sĩ chốt bản cuối): D1 tự trả lời từ L1 · D2 tự trả lời từ L2 có nguồn · D3 nháp + duyệt (bác sĩ có thể mở L2 cho loại cụ thể) · D4 luôn gọi người · D5 gọi bác sĩ ngay, không gọi LLM. Ma trận (độ sâu × mức × loại khách × giờ) là **cấu hình**, có màn chỉnh trên dashboard, bản mặc định đánh dấu "chờ bác sĩ duyệt".

## 7. Agent tự chọn nhân viên, tự đổi người, kết thúc ở số trực 24/24

**Hồ sơ nhân viên** `clinic.staff_profiles`: vai trò, **kỹ năng** (laser, mụn, nám, đặt lịch, thanh toán, khiếu nại…), ca trực, giờ làm, tải hiện tại, ngôn ngữ. `clinic.patient_ownership`: CSKH phụ trách và bác sĩ điều trị của từng khách.

**Chọn người** (xác định, không dùng LLM):
1. Lọc theo `required_skill` và `urgency` (D5 → chỉ bác sĩ; D4 → bác sĩ phụ trách hoặc bác sĩ trực).
2. Ưu tiên người **đang phụ trách khách này**.
3. Rồi người đang trực, còn tải, kỹ năng khớp.
4. Xếp **chuỗi ứng viên** 3–5 người; **phần tử cuối luôn là số Zalo trực 24/24**.

**Vòng chuyển giao:** gửi yêu cầu cho ứng viên hiện tại (push + hiện trong app, kèm tóm tắt) → Nhận → STAFF; Từ chối (lý do, có thể gợi ý người khác → đưa lên đầu chuỗi) → kế tiếp; im lặng quá SLA → kế tiếp. SLA mặc định: khẩn 5 phút, thường 30 phút, ngoài giờ: đến đầu ca kế (cấu hình). Lý do từ chối dùng để cập nhật hồ sơ kỹ năng theo thời gian.

**Số trực 24/24** (`clinic.on_call_contacts`: số Zalo, người phụ trách, lịch hiệu lực): lưu trong DB, chỉnh trên dashboard, **không nằm trong code/repo**. **Mọi agent đọc cấu hình này mỗi lượt** (đổi số là có hiệu lực ngay). Với D5 ngoài giờ: chuyển yêu cầu cho số trực và gửi khách **tin template** có số trực + hướng dẫn cấp cứu chung (không nội dung y khoa do LLM viết). Với D3–D4 ngoài giờ: chuyển số trực, khách nhận tin giữ chỗ có mốc giờ phản hồi. Log mỗi lần dùng số trực.

## 8. Nhắc theo lịch khi hội thoại đang ở STAFF

- Mọi nhắc đến hạn của khách đó bị **tạm dừng**: không gửi, không tự thành việc.
- Hiện trên dòng thời gian của nhân viên phụ trách dưới nhãn "đã tạm dừng", kèm nội dung soạn sẵn để gửi tay nếu muốn.
- Khi trả về AUTO, agent **đối soát**: nhắc đã quá hạn và hết ý nghĩa → bỏ (ghi log); nhắc còn giá trị → gửi lại theo mốc gần nhất kèm nhãn "nhắc trễ, lịch gốc …" (luật zalo-agent).
- Nếu khách trả lời một tin trong lúc STAFF, câu trả lời đi về nhân viên; agent không tự xử lý.

## 9. Agent chuyên môn mà care_agent gọi (độ sâu 1)

| Agent | Việc | Tool | Policy |
|---|---|---|---|
| **SchedulerAgent** | Tìm slot, đề xuất lịch, tạo lịch nháp | `appointment.search_slots`, `appointment.book` (cần duyệt trừ khi L1 xác nhận slot khách chọn) | `staff_assistant` |
| **KnowledgeAgent** | Tra KB có trích nguồn; nạp tài liệu; gắn quyền | `kb_search`, `kb_ingest`, `kb_list` | `staff_assistant` |
| **ReviewerAgent** | Chấm nháp theo checklist bác sĩ: có nguồn? có chẩn đoán? có PII? đúng template? phân loại độ sâu đúng? | chỉ đọc | chỉ đọc |

care_agent là người khởi xướng; không có coordinator tổng. Handoff giữa agent dùng `TaskResult{summary, artifacts[], citations[], needs_human, confidence}` (pydantic), coordinator chỉ đọc trường. Ngân sách mỗi lượt: tối đa 3 agent chuyên môn, 8 bước tool mỗi agent, trần token, deadline (3 phút tương tác, 20 phút việc nền) → vượt là `needs_human`.

## 10. Dữ liệu

```
agent.care_agents           patient_id (unique) · profile · autonomy_levels (jsonb theo loại hành động)
                            · autonomy_override {level, until} · trust_scores · preferences · last_tick_at · paused
agent.care_memory           care_agent_id · fact · source (patient|staff|doctor_edit) · valid_until   (không chứa hồ sơ y khoa; đã che PII)
agent.conversation_control  patient_id · state (AUTO|HANDOFF_ROUTING|STAFF) · since · staff_owner · release_note · auto_release_after (null)
agent.handoff_requests      id · patient_id · reason · depth · confidence · required_skill · urgency
                            · candidates[] · current_idx · accepted_by · outcome · timestamps
agent.tasks                 id · parent_id · care_agent_id · agent_id · status · input · result(TaskResult) · tokens · cost · timing · error
agent.actions_log           care_agent_id · action_type · depth · auto_sent|reviewed|paused · reviewer_edit_diff · at
agent.skills                name · instruction · classifier_config · enabled_for_profiles
clinic.staff_profiles       user_id · role · skills[] · shift · capacity · languages
clinic.patient_ownership    patient_id · cs_owner · doctor
clinic.on_call_contacts     zalo_number · owner · valid_from · valid_to · active
```

Ngữ cảnh lâm sàng vẫn ở `clinic.*`, agent đọc qua `actions/`.

## 11. Lan can

1. Policy profile áp theo agent; care_agent kế thừa profile nghiêm nhất của agent chuyên môn nó gọi; với khách luôn là `patient_channel`.
2. Độ sâu giao việc = 1; agent chuyên môn không có tool `delegate`.
3. Che PII trước khi vào bất kỳ agent; agent chỉ cầm `patient_ref`.
4. Trần tin chủ động theo khách/ngày (gói S), `marketingOptOut`, sinh nhật không tự gửi.
5. Lượt theo lịch cắt `schedule_task`, `save_memory` (luật zalo-agent).
6. Kill switch theo khách, theo agent, theo toàn hệ thống trên dashboard.
7. Audit mọi lượt, mọi chuyển trạng thái, mọi đổi mức tự chủ, mọi lần dùng số trực.

## 12. Giao diện (bổ sung gói E)

- **Dòng thời gian agent theo khách**: đã gửi gì, nháp chờ gì, vì sao chuyển người, nhắc đang tạm dừng.
- **Yêu cầu đang chờ tôi**: Nhận / Từ chối (lý do, gợi ý người khác), tóm tắt ngữ cảnh.
- **Trả lại cho agent**: ghi chú + chọn mức tự chủ (giữ / hạ có thời hạn).
- **Nói với agent** của khách: lệnh tự do, ghi vào `care_memory` nguồn `staff`.
- **Quản trị**: hồ sơ kỹ năng và ca trực; số trực 24/24; ma trận ngưỡng độ sâu (có cờ "chờ bác sĩ duyệt"); SLA; khung giờ gửi; cảnh báo (agent bị hạ mức, khách không phản hồi nhiều lần, cờ đỏ, dùng số trực).

## 13. Các bước

Mỗi bước có một recipe riêng cho subagent trong `pema-agent/recipes/M/` (`00-README.md` nêu thứ tự, phụ thuộc, vị trí code; `_REPORT-TEMPLATE.md` là mẫu báo cáo). Prompt spawn chỉ cần: "Follow `pema-agent/recipes/M/<file>.md`".

| Bước | Nội dung | Nghiệm thu |
|---|---|---|
| M1 | Schema mục 10; pairing tự động khi tạo hồ sơ; migration | pytest; RLS theo clinic_id |
| M2a | Vòng lượt theo sự kiện + tick 6h; hàng đợi ưu tiên; khung giờ gửi; trần tin/khách | test với clock giả |
| M2b | Máy trạng thái kiểm soát; skill `handoff` + bộ phân loại độ sâu; ma trận cấu hình | test: D5 không gọi LLM; chỉ nhân viên trả về AUTO |
| M2c | Định tuyến nhân viên; chuỗi ứng viên; SLA; số trực 24/24 luôn là cuối chuỗi; tạm dừng và đối soát nhắc | test: hết chuỗi luôn tới số trực; nhắc tạm dừng không gửi |
| M3 | Bậc tự chủ L0–L2; cộng/hạ điểm; hạ mức có thời hạn; kill switch | test chuyển mức |
| M4 | Gọi Scheduler/Knowledge/Reviewer; `TaskResult`; ngân sách | test: vượt ngân sách → needs_human |
| M5 | FE mục 12 | build/lint; 5 viewport |
| M6 | Eval: tỷ lệ nháp duyệt không sửa theo loại; độ chính xác phân loại độ sâu so với nhãn bác sĩ; độ trễ; chi phí/khách/tháng | báo cáo số đo thật trên Ollama |

## 14. Phụ thuộc và rủi ro

- Cần D1 (engine, `HarnessProcessor`), S (scheduler, caps, `bot_enabled`), P (profiles, cờ đỏ, PII, xác minh zalo_uid), B1 (actions, RBAC), E (khung FE).
- Zalo chưa có OA: Bot API chỉ nhắn được khách đã nhắn bot; khách khác → agent tạo việc cho CSKH gửi tay với nội dung soạn sẵn.
- Độ trễ trên RTX 3060 với Qwen3-8B: đo luồng khách nhắn → trả lời; nếu > 60 giây, rút bớt agent chuyên môn hoặc đẩy sang nền.

## 15. Quyết định đã chốt (2026-10-02)

1. Ngưỡng độ sâu, ma trận tự chủ, N để lên L2: **bác sĩ chốt**; code chỉ có bản mặc định "chờ duyệt".
2. Trong STAFF: **agent không gửi nhắc theo lịch**; tạm dừng, đối soát khi về AUTO.
3. Trả về AUTO **kèm hạ mức có thời hạn**: có.
4. Chuyển người là **quyết định của agent** (skill `handoff`), không có nút "gặp người".
5. Agent **tự chọn và tự đổi nhân viên**; chuỗi luôn kết thúc ở **số Zalo trực 24/24** do phòng khám cung cấp, mọi agent đọc từ cấu hình mỗi lượt.
6. Multi-agent ở phía sau care_agent (Scheduler/Knowledge/Reviewer), không bao giờ nói chuyện trực tiếp với khách theo nhóm.

Việc còn chờ phòng khám cung cấp: ma trận ngưỡng cuối, bộ ca mẫu gán nhãn độ sâu để eval, danh sách kỹ năng nhân viên, số trực 24/24.
