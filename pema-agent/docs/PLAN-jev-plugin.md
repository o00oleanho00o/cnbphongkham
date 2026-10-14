# Kế hoạch: plugin `jev` (bộ chấm TypeSafe Jev) và Kho tri thức dùng nó để xếp lại, lọc kết quả tìm

**Trạng thái (2026-10-14): bước 0 đến 4 đã làm; bước 4 chạy bằng khóa của user, kết quả ở mục 7. Jev vẫn tắt mặc định.** Bản nháp bộ lọc
đặt trong `knowledge` (có trước khi duyệt) đã bị gỡ, code làm lại đúng kế hoạch. Xem "Đã làm" ở mục 3.

Nguồn: tài liệu TypeSafe (`docs.typesafe.ai`: API `/v1/systemone`, câu hỏi `noul`/`choice`/`score`, cookbook
"Classifying RAG passages" và "Re-ranking"), video "Build RAG with JEV" (Prompt Engineering) và notebook của video
(`jev_reranker_rag.py`, "The Steerable Reranker"): `criteria` làm luật, metadata của đoạn nằm trong `state`, xếp lại
theo xác suất, hai hàm `ask` / `fanout` (64 luồng) và bộ đếm token dùng cho mọi bài toán; 1 đến 21 câu hỏi trong một
request vẫn khoảng 150 ms. Trên bộ thử của họ (24 câu hỏi đáp tiếng Anh tự viết, "BM25" là đếm từ trùng, top-6) độ
đúng vị trí số 1 lên từ 21% tới 54%. Số đó là của họ, với cách tìm rất thô; ta đã có tìm theo nghĩa cộng từ khóa nên
không mong mức tăng như vậy.

## 1. Mục tiêu

- Agent chỉ nhận những đoạn tài liệu **đủ căn cứ** để trả lời, xếp đoạn trả lời thẳng lên đầu; không đoạn nào đủ thì
  nói chưa có thông tin thay vì đoán (giá, chính sách sai là lỗi nặng nhất của phòng khám).
- Jev là **một plugin riêng**, cắm vào như `embeddings`: bật/tắt độc lập, giữ khóa riêng, plugin khác dùng qua dịch vụ.
  Tắt `jev` thì mọi thứ chạy y như hôm nay.
- Câu hỏi ngắn, mơ hồ được tìm theo vài cách trong một lần gọi tool (thay cho Multi-Query gọi thêm model).

Không phải mục tiêu: dùng Jev thay luật cứng (bác sĩ duyệt đơn, cờ đỏ, đồng ý chụp ảnh, nhắn bệnh nhân).

## 2. Kiến trúc

```
kb_search(queries[1..3])
  ├─ mỗi câu: từ khóa + vector (song song)      ← Bước 0
  ├─ gộp, bỏ trùng, xếp như hiện nay
  ├─ ctx.use("judge") ── có? ──► plugin jev ──► api.typesafe.ai/v1/systemone (mỗi đoạn 1 request, song song)
  │                     không? ─► bỏ qua, như hôm nay
  ├─ knowledge tự quyết: bỏ / xếp lại theo điểm luật xếp hạng      ← Bước 2
  └─ gói theo ngân sách ký tự → agent
```

### 2.1 Hợp đồng dịch vụ (lõi, `agent_app/plugins/services.py`)

Thêm cạnh `EMBEDDINGS`:

- `JUDGE = "judge"`.
- `JudgeService` (Protocol, `runtime_checkable`), dịch vụ chung: chỉ hỏi Jev, không chứa luật RAG (đúng như hai hàm
  `ask` / `fanout` của notebook):
  - `async ready() -> bool`: có khóa và đang dùng được.
  - `async ask(states: Sequence[JsonValue], questions: Mapping[str, Question], *, timeout_s) -> list[dict[str, Answer]]`:
    cùng bộ câu hỏi cho nhiều `state`, chạy song song (giới hạn số request đồng thời), trả theo thứ tự.
  - `Question`/`Answer`: dict theo đúng API TypeSafe (`type`, `instructions`, `criteria`; `noul` | `choice` +
    `probabilities` + `confidence` | `score` + ...). Không bọc thêm kiểu riêng.
- `JudgeUnavailableError(message)`: chưa có khóa, sai khóa, hết tiền, quá giới hạn, quá giờ, trả lời không đọc được.
  Người gọi luôn có đường lui.

Câu hỏi và `criteria` thuộc về **plugin dùng** (knowledge biết thế nào là "đủ căn cứ"), không thuộc `jev`.

### 2.2 Plugin `jev` (`plugins/jev/`)

- `plugin.toml`: không migration (chỉ dùng storage của plugin), cài đặt `timeout_s` (mặc định 4), `concurrency`
  (mặc định 8).
- **Hạn mức token mỗi ngày sửa được trên trang "Jev"** (lưu trong storage của plugin), mặc định 2.000.000 token đầu
  vào/ngày ≈ 0,084 USD theo giá $42/1 tỷ token; 0 nghĩa là không giới hạn.
- Khóa TypeSafe mã hóa trong storage (như khóa embedding), không bao giờ trả về; model mặc định `jev-latest`.
- Gọi REST bằng `httpx` async (không thêm gói `typesafe-sdk` mà notebook dùng: cả việc chỉ là một endpoint, và SDK
  của notebook chạy bằng luồng). 429/529 thử lại một lần có giãn cách nếu còn thời gian; 401/403 báo "Khóa sai, hết
  hạn hoặc hết tiền".
- Đếm token theo ngày (từ `usage` của mỗi câu trả lời); chạm trần thì `JudgeUnavailableError("Đã dùng hết hạn mức
  hôm nay")` cho tới ngày sau.
- Route `/v1/plugins/jev/settings` (GET/PATCH), `/test` (một câu thử), `/usage` (token và số lượt 7 ngày).
- Trang "Jev" (UI riêng, như các plugin khác): khóa, model, hạn mức ngày, nút "Kiểm tra kết nối", bảng đã dùng
  (lượt gọi, token, ước tính USD), dòng ghi rõ dữ liệu gửi tới TypeSafe (Mỹ).
- Không đăng ký tool, hook hay prompt: chỉ là dịch vụ.

### 2.3 Kho tri thức dùng dịch vụ

- Thay hai công tắc **không có tác dụng** của thẻ "Gán nhãn và xếp lại" (`labelling.enabled`, `labelling.rerank`:
  được lưu nhưng không code nào đọc). Công tắc "Xếp lại kết quả tìm" thành "Xếp lại và lọc bằng Jev", kèm ngưỡng
  Chặt/Vừa/Rộng; chỉ bật được khi plugin `jev` đang chạy (không có thì ghi "Bật plugin Jev trước"). Công tắc "Gán
  nhãn đoạn khi nạp" tạm ẩn cho tới mục 5.1.
- Bỏ phần gọi HTTP và khóa khỏi bản nháp trong `knowledge`; giữ phần quyết định (`route`) và các bước hiện trên
  "Thử tìm".

## 3. Các bước

**Đã làm (2026-10-14, nhánh `feat/knowledge-embedding`, chưa đẩy):**

- Bước 0: `kb_search` nhận `query` và tối đa 2 `alternatives` (thay cho `queries` của kế hoạch, để `query` cũ vẫn chạy);
  mỗi cách hỏi tìm từ khóa và vector song song, gộp theo hạng (`fusion.rank_fusion`, RRF); hướng dẫn agent viết thêm cách
  hỏi khi câu ngắn, mơ hồ. Trace có `queries`. Tool `kb_search` được chờ tối đa 20 giây (trước 15) vì thêm bước chấm.
- Bước 1: lõi `JUDGE`, `JudgeService`, `JudgeUnavailableError` (`agent_app/plugins/services.py`); plugin `jev`
  (`plugins/jev/`: `client.py` gọi `POST /v1/systemone` bằng `httpx`, mỗi state một request, song song, thử lại 429/529
  một lần; `plugin.py` khóa mã hóa, hạn mức token mỗi ngày (mặc định 2.000.000, 0 là không giới hạn), sổ dùng 14 ngày;
  `routes.py` `/settings`, `/test`, `/usage`). Không migration. 17 test.
- Bước 2: `knowledge/judging.py` (một câu `noul` `ranks_top` mỗi đoạn; xếp theo điểm, từ chối khi đoạn tốt nhất dưới sàn
  của mức chặt strict 0,30 / medium 0,10 / loose 0,05, bỏ đoạn dưới 0,2 lần đoạn tốt nhất; bản đầu cắt từng đoạn ở 0,55 và
  có thêm hai câu, đã thay sau khi đo thật, xem mục 7); `Searcher.search(judge=...)`; cài đặt `judging {enabled, level}`
  thay `labelling.rerank` (hai công tắc cũ không có tác dụng đã bỏ); "Thử tìm" có hai bước "Bộ chấm Jev: giữ / bỏ"; không
  đoạn nào đủ căn cứ thì `kb_search` bảo agent nói chưa có thông tin và ghi vào "câu hỏi chưa có tài liệu". 18 test (đơn
  vị + hai plugin chạy cùng nhau với TypeSafe giả).
- Bước 3: trang "Jev" (`plugins/jev/ui`), thẻ "Xếp lại và lọc bằng Jev" trong cài đặt Kho tri thức (bỏ thẻ "Gán nhãn
  và xếp lại"), profile `clinic` bật plugin `jev`, `agent.Dockerfile` build `jev/ui`. 11 test UI cho `jev`, 127 cho
  `knowledge`; `pnpm run build` qua, chưa mở thử trong trình duyệt.
- Bộ đo: `scripts/kb_bench.py --judge [--lang vi] [--level ...]` lặp mỗi lượt chạy với Jev bật rồi so (tài liệu đúng bị
  mất, câu hỏi không có đáp án bị từ chối, token, tiền); thêm tập C gồm 8 câu tài liệu không trả lời được.

**Khác với kế hoạch lúc viết:**

- `state` gửi `doc_code`, `title`, `section`, `text` và `services` (khi có); không gửi `kind` hay `effective_from`: tìm
  kiếm chỉ trả tài liệu đang dùng và còn hiệu lực đúng ngày hỏi (`lifecycle` active, đã xử lý xong, ngày hiệu lực), nên
  Jev không cần xét hiệu lực. Kho **không xét duyệt**: tìm kiếm không đọc `approved` (tài liệu thêm vào mặc định coi là
  đã duyệt, đúng ý user là chưa cần duyệt), nên không gửi và `criteria` không nhắc "duyệt" (xem `knowledge/judging.py`).
  (Bản ghi trước của dòng này nói kho bỏ tài liệu "chưa duyệt": sai, đã sửa 2026-10-14.)
- Chỉ 10 đoạn đầu được chấm; đoạn ngoài 10 đầu không tới agent khi Jev đã chấm.
- Dịch vụ `judge` nhận bộ câu hỏi từ nơi gọi; `JudgePlan.questions` cho phép bộ đo thử câu hỏi tiếng Việt.

| Bước | Việc | Xong khi |
|---|---|---|
| 0 | `kb_search` nhận `queries` (1-3 câu: câu chính + biến thể do agent viết trong cùng lời gọi); mỗi câu tìm từ khóa và vector song song, gộp, bỏ trùng; hướng dẫn agent: câu ngắn, mơ hồ thì viết thêm biến thể. Giữ `query` cũ cho tương thích. | Test: một câu mơ hồ tìm được đoạn mà câu gốc không tìm được; trace ghi số câu. |
| 1 | Lõi: `JUDGE`, `JudgeService`, `JudgeUnavailableError`. Plugin `jev`: khóa, gọi API, song song, thử lại, hạn mức ngày, route, trang. | Test với TypeSafe giả: gửi đúng, khóa không lộ, lỗi thành câu đọc được, chạm hạn mức, plugin tắt thì `ctx.use` trả `None`. |
| 2 | `knowledge`: mỗi đoạn trong 10 đoạn đầu hỏi một `noul` `ranks_top` có `criteria` (mục 4); xếp theo điểm, bỏ đoạn kém hơn hẳn đoạn tốt nhất; đoạn tốt nhất dưới sàn của mức chặt thì không đưa gì và báo agent "không đủ căn cứ", ghi vào "câu hỏi chưa có tài liệu". Jev lỗi, chậm, không có thì dùng kết quả như hôm nay. | Test: xếp lại đúng, bỏ đúng, đường lui, trace có `judged`; "Thử tìm" có bước "Bộ chấm Jev: giữ" / "bỏ". Đo thật ở mục 7. |
| 3 | UI: trang "Jev"; thẻ "Xếp lại và lọc bằng Jev" trong cài đặt Kho tri thức; ghi `web-design-changes.md`. | `pnpm run build` qua. |
| 4 | Thử thật: 20-30 câu hỏi thật của phòng khám, chạy tắt / bật Jev, so: đoạn đúng có lên đầu không, câu nào bị chặn nhầm, độ trễ, token. Câu hỏi và `criteria` thử cả tiếng Anh và tiếng Việt. | Bảng kết quả trong mục 7; quyết định bật thật hay không và ngưỡng nào. |

Khóa cho bước 4: user nhập trên trang "Jev" sau khi build lại, hoặc đặt `TYPESAFE_API_KEY` trên máy cho một lần chạy
thử; không ghi khóa vào code hay git.

## 4. Câu hỏi gửi Jev (bước 2, bản sau khi đo)

Mỗi đoạn một request, **một** câu `noul` (luật xếp hạng của phòng khám, viết cố định trong `knowledge/judging.py`):

- `ranks_top`: "Should this passage be ranked top for the customer's question under the clinic's policy?";
  `criteria.true`: "It states the specific fact the question asks for (a price, a duration, a condition, a step) for
  the service the question is about, as an official clinic document would";
  `criteria.false`: "It only shares words or the topic, or it is about a different service, or it is general
  background that does not state the fact asked, or it answers a different question".

`state` là **một chuỗi** (như notebook), không phải object:

```
Customer question: <câu tìm của agent>
Other ways the customer may have asked it: <alternatives, khi có>

Passage (document: <tiêu đề>; section: <mục>):
<nội dung đoạn>
```

Cách dùng điểm (mục 7 giải thích vì sao): sắp đoạn theo điểm; nếu đoạn tốt nhất dưới **sàn** của mức chặt (chặt 0,30,
vừa 0,10, rộng 0,05) thì không đưa đoạn nào cho agent; nếu không thì bỏ đoạn dưới 0,2 lần điểm đoạn tốt nhất.

Bản đầu có thêm hai câu `is_relevant` ("lạc chủ đề") và `contains_prompt_injection` ("cố điều khiển trợ lý", cookbook
của TypeSafe) và cắt từng đoạn theo ngưỡng; đã bỏ vì: hai câu thêm không cải thiện gì, và câu "điều khiển" gắn nhầm cả
những câu chính sách hợp lệ ("Trợ lý không tự quyết định hoàn tiền…"). Tài liệu trong kho do phòng khám viết (nguồn
tin cậy); nếu sau này nhận tài liệu từ bên ngoài thì cần một cách kiểm riêng.

## 5. Để sau (đã ghi, chưa làm)

1. **Câu hỏi mẫu cho mỗi đoạn lúc nạp (thay HyDE).** Khi nạp, model chat viết 3-5 "câu khách có thể hỏi" cho mỗi đoạn,
   nhúng cùng đoạn (và đưa vào từ khóa). Làm một lần lúc nạp, lúc tìm không tốn gì. Dùng lại chỗ "Gán nhãn đoạn khi
   nạp" (mục 2.3) và chọn model ở đó. Làm khi bước 4 cho thấy tìm còn hụt (đoạn đúng không có trong 10 ứng viên).
   Không làm HyDE (sinh câu trả lời giả lúc tìm): thêm một lượt model mỗi lần tìm và câu giả bịa số liệu.
2. **Jev cho kịch bản mẫu** (`conversations`): lọc kịch bản thật sự giống tình huống trước khi đưa vào khối "Kịch bản
   mẫu".
3. **Kiểm câu trả lời trước khi gửi** (cookbook "Double-checking citations"; notebook dòng 739-756): tách các câu có
   số liệu trong câu trả lời, mỗi câu kèm đoạn nguồn, hỏi một `choice` "How does the cited passage relate to the claimed
   statement?" với `supports` / `contradicts` / `unaddressed`; `contradicts` hay `unaddressed` thì chặn hoặc báo nhân
   viên. Cần hook trước khi gửi.
4. **Ô "luật xếp hạng"** để phòng khám tự sửa `criteria` của `ranks_top` (bản đầu đã viết cố định ở bước 2).
5. **Lọc tin của khách khi vào** (notebook dòng 714-736): một request hai `noul` (cố vượt luật, xin điều nguy hại) và
   một `score` mức rủi ro 0-4; đứng cạnh `scan_for_threats` đang có, không thay nó.
6. **Phân loại tin** (cần nhân viên, khiếu nại, cờ đỏ) bằng `choice`: chỉ làm khi có luật cứng đứng sau.
7. **Bộ chấm chạy tại chỗ thay TypeSafe** (user, 2026-10-14: dữ liệu ra nước ngoài tạm chấp nhận, xử lý sau nếu có
   model local). Dịch vụ `judge` không gắn với TypeSafe, nên một plugin khác (model phân loại chạy local, cùng hợp đồng
   `ask`) có thể thay `jev` mà Kho tri thức không phải sửa.

## 6. Rủi ro

- **Tiếng Việt chưa được TypeSafe nói gì** (model huấn luyện trên dữ liệu tổng hợp): bước 4 quyết định; chặn nhầm thì
  agent hay nói "chưa có thông tin". Ngưỡng chỉnh được, tắt được.
- **Dữ liệu ra nước ngoài:** câu tìm và đoạn tài liệu tới TypeSafe (Mỹ). Câu tìm có thể lẫn chi tiết của khách. User
  tạm chấp nhận; hướng xử lý về sau ở mục 5.7.
- **Phụ thuộc dịch vụ mới** (mở từ 15/9/2026, mã đóng): luôn có đường lui, thời gian chờ 4 giây.
- **Chậm thêm:** 10 request song song, TypeSafe nói 70-500 ms; tool `kb_search` có 15 giây, vector 10 giây: có thể cần
  hạ chờ vector hoặc nâng giới hạn tool.
- **Tiền:** hạn mức token theo ngày (mặc định 2 triệu, sửa trên trang "Jev"); ước tính mỗi lần tìm ≈ 10 đoạn × 600
  token ≈ 6.000 token ≈ 0,00025 USD, tức hạn mức mặc định đủ khoảng 330 lần tìm mỗi ngày.

## 7. Kết quả thử thật (2026-10-14, khóa TypeSafe của user, jev-1.13.0)

Bộ thử: 22 tài liệu demo Pema (209 đoạn), 30 câu hỏi trả lời được (tập A, B của `scripts/kb_bench_pema.jsonl`) và 8 câu
tài liệu không trả lời được (tập C), nền là tìm từ khóa (chưa thử tìm theo nghĩa vì máy này chưa có khóa embedding).
Lệnh: `scripts/kb_bench.py --modes keyword --judge --lang en --level medium`. Cả loạt khoảng 370 request, 200.000 token,
**0,0085 USD**; độ trễ Jev 0,7 giây mỗi câu hỏi (10 đoạn song song), ở mức vừa.

| | top1 (30) | top3 | top6 | MRR | tài liệu đúng bị mất | tập C bị từ chối (8) | đoạn đưa agent |
|---|---|---|---|---|---|---|---|
| không Jev | 16 | 24 | 25 | 0,667 | – | 0 | 6 |
| **Jev, tiếng Anh, vừa** | **19** | **26** | **26** | **0,750** | **0** | **5** | ~3,6 |
| Jev, tiếng Anh, rộng | 19 | 26 | 26 | 0,750 | 0 | 4 | ~3,6 |
| Jev, tiếng Anh, chặt | 18 | 24 | 24 | 0,700 | 2 | 5 | ~3 |
| Jev, tiếng Việt, vừa | 18 | 26 | 26 | 0,722 | 0 | 5 | ~3,6 |

Điều rút ra:

- **Có ích:** xếp lại đưa tài liệu đúng lên đầu (top1 16 → 19), không mất tài liệu đúng nào ở mức vừa, và 5 trong 8 câu
  không có đáp án được từ chối (agent nói chưa có thông tin) thay vì nhận đoạn không liên quan; agent đọc ít chữ hơn.
- **Cách dùng điểm quan trọng hơn câu hỏi.** Lần đo đầu (3 câu hỏi, cắt từng đoạn ở 0,55) **tệ hơn** không có Jev: top1
  15/30, top3 20/30, mất 6 tài liệu đúng. Lý do: nhiều đoạn của kho demo là dòng "Mã dữ kiện / Giá trị chuẩn" rất ngắn
  nên Jev cho điểm thấp (0,1 đến 0,4) dù là đoạn đúng; chỉ đoạn tự đủ nghĩa (câu hỏi đáp) mới đạt 0,9. So sánh điểm
  giữa các đoạn (xếp hạng) vẫn đúng, còn ngưỡng tuyệt đối thì sai. Vì vậy: xếp theo điểm, chỉ từ chối khi cả đoạn tốt nhất
  cũng thấp, bỏ đoạn kém hơn hẳn.
- **Câu `ranks_top` hơn câu "trả lời thẳng" của notebook** (top1 11 đến 12 so với 17 khi cùng cắt từng đoạn ở ngưỡng 0,2; đo offline từ điểm thô của cùng 38 câu).
- **Tiếng Anh nhỉnh hơn tiếng Việt một chút** (top1 19 so với 18, MRR 0,750 so với 0,722); giữ tiếng Anh.
- **Chưa thể kết luận chắc:** số ngưỡng (sàn 0,10 và 0,2 lần đoạn tốt nhất) được chọn trên chính 38 câu này, nên số trên
  là cận trên; 8 câu tập C có 3 câu vẫn lọt (agent vẫn nhận đoạn không liên quan); chưa đo với tìm theo nghĩa (hybrid),
  chưa đo cả agent trả lời đúng hay sai từ đầu đến cuối; chưa thử trên câu hỏi thật của phòng khám.
- Một lần gọi bị TypeSafe trả HTTP 499 (ngắt giữa chừng); đã coi như lỗi tạm thời, thử lại một lần.

Cách chạy lại (khóa trong biến môi trường, không ghi file):

```
cd pema-agent/backend/apps/agent
TYPESAFE_API_KEY=... uv run python scripts/kb_bench.py --docs "E:/Desktop/data test/AgentRAG_Pema_Demo/01_NAP_EMBEDDING" \
    --questions scripts/kb_bench_pema.jsonl --modes keyword --judge --lang en --level medium
# thêm BEEKNOEE_API_KEY=... và --modes keyword,hybrid để thử cả tìm theo nghĩa
```

## 8. Đã chốt (user, 2026-10-14)

1. Vừa xếp lại vừa lọc.
2. Câu hỏi và `criteria` bằng tiếng Anh; bước 4 thử cả tiếng Việt.
3. Jev bỏ hết đoạn thì agent nói chưa có thông tin và đề nghị chuyển nhân viên.
4. Gửi câu tìm và đoạn tài liệu tới TypeSafe (Mỹ): tạm chấp nhận, ghi lại để xử lý sau nếu có model local (mục 5.7).
5. Hạn mức token mỗi ngày cấu hình được trên giao diện, mặc định 2.000.000.
6. Thay hai công tắc không có tác dụng của "Gán nhãn và xếp lại" như mục 2.3.
7. Luật xếp hạng `ranks_top` như mục 4.
