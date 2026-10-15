# Kế hoạch: đo tìm kiếm đúng bản đang chạy, và mở đoạn nhỏ ra mục cha khi đưa agent đọc

Trạng thái: **bản 1 (2026-10-15), user duyệt ("ok làm đi"), đã làm xong bước 1 và bước 2; kết quả ở mục 7.** Hai bước
đầu của lộ trình gộp (bước 3 trở đi: đo câu trả lời (GĐ5 mở rộng), kiểm trích nguồn, reranker cục bộ; để sau). Không
bước nào cần gọi model; lượt đo có Jev (khoảng 0,02 USD) **chưa chạy** vì chưa có khóa TypeSafe.

Khác với bản duyệt: (1) bước 1B **cần migration** (`0003_bm25.sql`, hai cột `terms_len` và `term_counts`): bản thử đầu
không migration chậm 1,1 đến 1,4 giây mỗi lần tìm trên 5.000 đoạn; (2) tầng mục cha hạ từ 3 xuống 2 cấp tiêu đề, vì
nhiều tài liệu demo đi thẳng từ `#` xuống `###`; (3) hai đoạn tìm được trong cùng một tài liệu chỉ gộp khi đoạn sau
nằm trong cửa sổ của đoạn trước, không gộp cả tài liệu.

## 1. Vì sao

- **Số đo đang đo nhầm bản.** `scripts/kb_bench.py` nạp tài liệu vào `InMemoryKnowledgeStore`, nơi tìm từ khóa là BM25
  thật (`k1 = 1,2`, `b = 0,75`, độ hiếm của từ và độ dài đoạn tính trên các đoạn đang hiệu lực). Bản chạy trong Docker là
  `PostgresKnowledgeStore`: nối các từ của câu hỏi bằng `|` và xếp bằng `ts_rank_cd`, không có độ hiếm của từ, không
  chuẩn hóa theo độ dài đoạn. Vậy "top1 16 → 19 trên 30" (`PLAN-jev-plugin.md` mục 7) là số của BM25, chưa phải của bản
  đang chạy. Docstring đầu `plugins/knowledge/store.py` nói cả hai "tính từ hiếm nặng hơn": sai với Postgres.
- **Đoạn đúng mà quá ngắn.** Tài liệu cắt theo tiêu đề; mục dưới 60 ký tự ghép vào mục trước (`MIN_CHUNK_CHARS`), nên
  các mục kiểu "Giờ đóng cửa: Mã dữ kiện, Giá trị chuẩn, một câu" (150 đến 250 ký tự) đứng riêng. Tìm thì chính xác,
  nhưng đọc thì thiếu ngữ cảnh: Jev chấm các đoạn này 0,1 đến 0,4 dù là đoạn đúng, và agent chỉ thấy một dữ kiện, không
  thấy các dữ kiện cùng mục (giờ mở, giờ đóng, giờ nhận lịch cuối).

## 2. Bước 1: thước đo tìm kiếm cho đúng bản đang chạy

### 1A. Đo, chưa sửa plugin

- `kb_bench.py` thêm `--store memory|postgres` (mặc định `memory` như hôm nay) và `--db-url`. Với `postgres`: chạy
  migration của agent và của plugin `knowledge` lên database đó (như fixture của test DB), nạp 22 tài liệu demo bằng đúng
  đường nạp hiện có, tenant riêng `bench`.
- **An toàn:** chỉ nhận database có tên bắt đầu bằng `scratch_` hoặc `bench_`, nếu không thì dừng. Database tạo tạm trong
  container Postgres demo và xóa sau khi đo (như lần chạy test hôm 2026-10-15); không bao giờ là database demo.
- Chạy chế độ `keyword` trên cả hai store với 38 câu (`kb_bench_pema.jsonl`). Ra bảng top1, top3, top6, MRR, tập C, cùng
  danh sách câu đổi hạng giữa hai store.

### 1B. Quyết theo kết quả

- **Ngang nhau** (top1 lệch không quá 1 câu và MRR lệch không quá 0,02): chỉ sửa docstring, ghi kết quả. Xong bước 1.
- **Postgres kém hơn:** đưa BM25 vào Postgres, **một câu SQL**:
  - Ứng viên vẫn qua chỉ mục GIN như hôm nay (`c.terms @@ to_tsquery('simple', ...)`), cùng điều kiện "đang dùng"
    (`ready`, `active`, còn hiệu lực ngày hỏi).
  - CTE tính trên các đoạn đang dùng: N, độ dài trung bình, và độ hiếm của từng từ trong câu hỏi; tần suất của từ trong
    đoạn lấy từ vị trí lưu trong `tsvector` (`unnest(c.terms)`, số phần tử của `positions`); độ dài đoạn là tổng số vị
    trí. Công thức giống `InMemoryKnowledgeStore.search` (`_idf`, `BM25_K1`, `BM25_B` dùng chung).
  - Không migration, trừ khi `EXPLAIN ANALYZE` trên 209 đoạn chậm hơn 20 ms; khi đó thêm cột độ dài đoạn.
- **Đã kiểm, không vỡ gì khi đổi thang điểm:** điểm từ khóa chỉ dùng để xếp thứ tự, nhân `SERVICE_BOOST` 1,25 và hiển thị ở
  "Thử tìm" (2 chữ số); `min_score` chỉ áp cho nhánh vector; `vector_first` đặt đoạn chỉ có từ khóa dưới đoạn vector yếu
  nhất theo thứ hạng, không theo điểm.

### 1C. Giữ cho đúng về sau

- Test DB mới: một bộ đoạn nhỏ (từ hiếm, từ lặp, đoạn dài, đoạn hết hiệu lực) nạp vào cả hai store, phải ra cùng thứ tự
  và cùng điểm (sai số 1e-6). Ai đổi một bên thì test đỏ.
- Chạy lại bộ đo trên Postgres: số phải trùng bản in-memory.
- Sửa docstring `store.py`; `PLAN-jev-plugin.md` mục 7 ghi rõ đo trên store nào; `HANDOFF-agent-v2.md`.

## 3. Bước 2: "small-to-big", tìm bằng đoạn nhỏ, đưa agent đọc cả mục

**Không đổi cách cắt khi nạp** (không nạp lại, không migration, đoạn nhỏ vẫn giúp tìm chính xác). Chỉ đổi thứ được đưa
cho Jev và cho agent.

### 2A. Thước đo mức dữ kiện (trước khi code, không cần model)

- Thêm trường `facts` cho 30 câu trả lời được trong `kb_bench_pema.jsonl`: các "Mã dữ kiện" trả lời câu đó (ví dụ
  `DEMO-PEMA.hours.close`), lấy từ tài liệu. Câu dựa vào tài liệu không có mã (D10, D18, D20, D22) dùng một chuỗi ngắn
  chép đúng từ tài liệu.
- Chỉ số mới: **dữ kiện có trong gói** = mọi dữ kiện mong đợi xuất hiện trong đúng chữ agent nhận (`tool_text`), và **số
  ký tự của gói**. Đây là "context recall" của Ragas nhưng chấm bằng so chuỗi, không cần LLM.

### 2B. Cách mở rộng

- Sau `_spread`, trước Jev và `_packed`: mỗi đoạn tìm được thay bằng **nhóm của nó**: các đoạn cùng tài liệu có cùng mục
  cha (đường tiêu đề bỏ tiêu đề cuối), theo thứ tự trong tài liệu.
- Nhóm dài quá `MAX_GROUP_CHARS` (đề xuất 1.200) thì lấy đoạn tìm được cộng các đoạn kề gần nhất cho tới giới hạn.
- Hai đoạn tìm được cùng nhóm gộp làm một, giữ hạng tốt hơn. Đoạn giữ điểm của nó; chữ là chữ của nhóm; đường tiêu đề
  là mục cha.
- **Một truy vấn** lấy các đoạn cùng nhóm cho mọi kết quả (`source_id = ANY(:ids)`, lọc trong Python), không gọi DB trong
  vòng lặp. Hàm mới trong cả hai store, cùng test.
- Bật bằng tham số của `Searcher` và cờ `--expand` của bộ đo. **Không thêm công tắc trên giao diện.** Nếu đo thấy tốt hơn
  thì bật mặc định trong code (một dòng), không thì giữ tắt và ghi lại vì sao.

### 2C. Đo và quyết

- Chạy bốn cấu hình trên Postgres: từ khóa, từ khóa + mở rộng, và (tùy chọn, khoảng 0,02 USD) hai cấu hình đó có Jev mức
  vừa.
- Chỉ số: top1, top3, MRR, tài liệu đúng bị mất, **dữ kiện có trong gói**, số ký tự gói, điểm Jev của đoạn đúng.
- **Bật mặc định khi:** dữ kiện có trong gói tăng, không mất tài liệu đúng nào, gói không dài hơn quá 50 %.

## 4. Không làm trong kế hoạch này

- Tăng `MIN_CHUNK_CHARS` để ghép ngay khi nạp: phải nạp lại, làm tìm kém chính xác; small-to-big cho cùng lợi ích mà
  không mất độ chính xác.
- Semantic chunking, HNSW, HyDE, MMR (lý do trong trao đổi 2026-10-15).

## 5. File sẽ đụng

`scripts/kb_bench.py`, `scripts/kb_bench_pema.jsonl`, `plugins/knowledge/search.py`, `plugins/knowledge/store.py`
(docstring; SQL BM25 nếu 1B cần; hàm lấy nhóm), test mới trong `tests/knowledge/` (so hai store, mở rộng nhóm), tài liệu
(`PLAN-jev-plugin.md` mục 7, `HANDOFF-agent-v2.md`, file này). Không có thay đổi giao diện nên không ghi
`web-design-changes.md`.

## 6. Kiểm tra trước khi xong

Test của `tests/knowledge/` (gồm test DB trên database tạm), `ruff`, `pyright` cho các file đổi; full suite không chạy
(quy tắc `testing.md`), trừ khi user yêu cầu. Kết quả đo ghi vào mục 7 bên dưới khi có.

## 7. Kết quả (2026-10-15)

Bộ đo: 22 tài liệu demo (209 đoạn), 30 câu trả lời được + 8 câu không có đáp án, tìm từ khóa (chưa có khóa embedding),
database tạm `scratch_kb_bench` trong container Postgres demo (xóa sau khi đo). Lệnh:
`scripts/kb_bench.py --modes keyword --store postgres --db-url .../scratch_kb_bench [--expand-chars N] [--facts]`.

### Bước 1: bản Postgres kém hơn bản đã đo

| Cách tìm từ khóa | top1 | top3 | top6 | MRR |
|---|---|---|---|---|
| Bộ nhớ (BM25), số trong `PLAN-jev-plugin.md` §7 | 16 | 24 | 25 | 0,667 |
| **Postgres trước khi sửa** (`ts_rank_cd`, bản chạy trong Docker) | 14 | 20 | 24 | 0,606 |
| **Postgres sau khi sửa** (BM25 trong SQL) | 16 | 24 | 25 | 0,667 |

- Số "16 → 19 trên 30" của Jev là số của BM25 bản bộ nhớ; bản Postgres thật khi đó chỉ đạt 14. Từ nay hai bản cho cùng
  điểm (test `test_postgres_and_memory_score_keyword_search_the_same`).
- Cách làm: hai cột lưu sẵn cạnh `tsvector` (độ dài đoạn, số lần mỗi từ), ứng viên qua chỉ mục GIN, một câu SQL. Ba bảng
  thống kê trong câu SQL phải khai `MATERIALIZED`: không có, Postgres chạy lại chúng cho từng đoạn (1,1 đến 2,8 giây trên
  5.000 đoạn; 680 ms trên 209 đoạn khi chưa có thống kê). Có: 60 đến 140 ms trên 5.000 đoạn, 16 ms trên 209 đoạn. Lượt
  tìm đầu tiên sau khi nạp rất nhiều đoạn có thể chậm hơn đến khi Postgres tự `ANALYZE`.

### Bước 2: mở đoạn nhỏ ra mục cha (small to big)

Chỉ số mới: **dữ kiện có trong gói** = mọi "Mã dữ kiện" trả lời câu hỏi nằm trong chữ agent nhận (20 trong 30 câu có
dữ kiện rõ; 10 câu trả lời bằng văn xuôi không gán dữ kiện, không đoán).

| Giới hạn mục (ký tự) | top3 | dữ kiện trong gói | gói (ký tự, trung vị) | so với không mở rộng |
|---|---|---|---|---|
| tắt | 24 | 10/20 | 2.259 | – |
| 600 | 24 | 10/20 | 3.174 | +41 % |
| 800 | 25 | 12/20 | 4.421 | +96 % |
| 1.000 | 25 | 12/20 | 5.269 | +133 % |
| 1.200 | 25 | 14/20 | 5.606 | +148 % |

- **Kết luận: giữ tắt.** Mức nào đạt ngưỡng "gói không dài hơn quá 50 %" (600) thì không thêm dữ kiện nào; mức thêm được
  dữ kiện thì gói dài gấp rưỡi đến gấp đôi, tốn token mỗi lượt và chạm trần 6.000 ký tự của gói. Top1, MRR và tập C không
  đổi ở mọi mức.
- Trong 10 câu còn thiếu dữ kiện ở mức tắt: 6 câu tìm đúng tài liệu nhưng không đúng mục (ví dụ D13 có mặt, thiếu phí
  hủy muộn), 4 câu không tìm thấy tài liệu đúng (từ khóa không đủ). Mở rộng cứu được 4 trong 6 câu đầu ở mức 1.200.
- **Chưa đo, nên chưa bỏ:** mở rộng có Jev. Động cơ ban đầu là Jev chấm đoạn ngắn rất thấp; đoạn dài hơn có thể được chấm
  đúng hơn và bù lại chi phí gói. Cần khóa TypeSafe (khoảng 0,02 USD).
- Tham số `Searcher(expand_chars=N)` và cờ `--expand-chars N` của bộ đo giữ lại, mặc định tắt, không có công tắc trên
  giao diện.

### Còn lại

- Lượt đo có Jev (bốn cấu hình: từ khóa, từ khóa + mở rộng, mỗi cấu hình có và không có Jev, mức vừa).
- Bước 3 trở đi của lộ trình gộp: thước đo câu trả lời (GĐ5 mở rộng), kiểm trích nguồn, reranker cục bộ.
- Bản Docker cần build lại; `agent-migrate` chạy `0003_bm25.sql` (thêm hai cột và backfill) khi khởi động.
