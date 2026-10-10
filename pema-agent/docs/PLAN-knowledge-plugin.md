# Plugin `knowledge`: Agentic RAG cho agent (thiết kế, 2026-10-10)

Trạng thái: **user đã duyệt 4 câu hỏi mở (mục 16) ngày 2026-10-10; chưa code.** Viết sau khi bàn ở phiên
2026-10-10 (RAG vs Graph RAG vs Agentic RAG, RAG-Anything, Apache Doris, chi phí embedding, Docling). Mọi quy
tắc cũ của clinic API (`apps/api/pema/knowledge`) KHÔNG còn là ràng buộc; cái gì giữ lại là vì nó đúng với
thiết kế mới, không phải vì nó có sẵn.

## 0. Những điều đã chốt trong lúc bàn

| Việc | Chốt | Lý do ngắn |
|---|---|---|
| Lưu trữ | Postgres sẵn có + pgvector (image compose đã là `pgvector/pgvector`) | kho nhỏ (nghìn đoạn), một engine cho cả agent và tri thức; Doris để dành cho phân tích quy mô lớn |
| Embedding | **cục bộ**, Ollama `bge-m3`, **1024 chiều**, cosine | máy dev có RTX 3060 12 GB; câu hỏi bệnh nhân không rời máy; API (Gemini cắt 1024) là phương án khi máy chủ không có GPU, chỉ cần nhúng lại |
| Graph RAG | không làm ở bản đầu, chừa chỗ ở tầng retriever | câu hỏi của phòng khám chủ yếu một bước quanh "dịch vụ"; multi-hop nhẹ giải bằng nhãn + agent tìm nhiều lượt |
| RAG-Anything | không nhúng vào agent | phụ thuộc nặng (MinerU, LibreOffice, Python 3.10); nếu cần parser mạnh thì chạy container riêng, spike sau |
| Vị trí | plugin `knowledge` của `apps/agent`, độc lập, không gọi clinic API | "mọi thứ là plugin" |
| Tầng điều khiển | dùng vòng lặp sẵn có của agent (tool nhiều bước, trace, guard) | agentic = cách agent dùng tool, không cần lõi mới |

## 1. Bài toán thật

### 1.1 Câu hỏi sẽ gặp (kênh Zalo với bệnh nhân, kênh web/CLI với nhân viên)

| Nhóm | Ví dụ | Kiểu tìm |
|---|---|---|
| Giá, gói | "Laser nám bao nhiêu, có gói không?" | một bước, phải đúng số |
| Quy trình, thời gian | "Bớt Hori làm mấy buổi, cách nhau bao lâu?" | một bước |
| Chuẩn bị, chăm sóc sau | "Sau laser kiêng gì?" | một bước |
| Chống chỉ định, kết hợp | "Đang mang thai làm được không? Đang bôi retinol thì sao?" | hai bước: dịch vụ + điều kiện |
| So sánh | "Nám nên làm laser hay peel?" | nhiều nguồn, agent tổng hợp |
| Nhân viên hỏi | "Quy trình tư vấn khách nám như nào?" | một bước, nội dung nội bộ |
| Ngoài tài liệu | chẩn đoán, hứa kết quả, hỏi lung tung | phải từ chối đúng cách |

Kết luận: 80% là một bước nhưng **phải đúng số và đúng tên dịch vụ**; phần còn lại là multi-hop nhẹ quanh
**dịch vụ**. Đơn vị tri thức của phòng khám là *dịch vụ*, không chỉ là *tài liệu*.

### 1.2 Tài liệu thật trông thế nào (đọc thử "Cẩm nang dịch vụ Nám - bớt Hori.pdf", 19.500 ký tự)

- Một cẩm nang cho một (nhóm) dịch vụ, cấu trúc lặp lại: TỔNG QUAN (giới thiệu, nguyên nhân, triệu chứng, chỉ
  định) → NỘI DUNG (công nghệ, liệu trình "8-10 lần, 1 tháng/lần", quy trình điều trị, hướng dẫn sau điều trị,
  hiệu quả) → QUY TRÌNH TƯ VẤN (kịch bản lễ tân, bác sĩ) → …
- **Trích PDF ra là mất tiêu đề:** tiêu đề chỉ còn là dòng chữ in hoa hoặc dòng ngắn ("Nguyên nhân",
  "Quy trình điều trị"). Bộ chia đoạn cũ chỉ nhận tiêu đề Markdown `#`, nên với PDF nó cắt mù. → cần bước
  **dựng lại cấu trúc** (mục 3.2).
- Mỗi trang lặp lại đầu trang "CẨM NANG ĐIỀU TRỊ NÁM - HORI / Tài liệu nội bộ Pema Clinic" → phải lọc.
- **Trong cùng một tài liệu có phần cho bệnh nhân (quy trình, chăm sóc sau) và phần nội bộ** ("Khách hàng có
  điều kiện kinh tế hay không?"). User chốt: cờ đối tượng ở mức **tài liệu** (không gắn nhãn theo đoạn). Hệ
  quả: một cẩm nang trộn hai phần phải được **tách thành hai nguồn** trước khi cho bệnh nhân thấy; trang Chi
  tiết nguồn hỗ trợ việc này (mục 3.2: sửa bản dựng cấu trúc → xóa các mục nội bộ → nạp lại, hoặc "Tách mục đã
  chọn thành nguồn mới"). Mặc định an toàn: nguồn mới là `for_patients = false`.
- Bảng giá sẽ ở XLSX (fixture `danhsach.xlsx`, `excel-o-rong-co-dinh-dang.xlsx` đã có): mỗi dòng là một
  dịch vụ + giá; không được cắt đôi bảng.

## 2. Kiến trúc: 5 tầng, tách rời

```
5  ĐIỀU KHIỂN   agent: nhận diện dịch vụ -> tìm -> tự chấm -> tìm lại/đọc thêm -> trả lời có nguồn | từ chối
4  CÔNG CỤ      kb_search · kb_read · (kb_services qua prompt)      <- giao diện duy nhất agent nhìn thấy
3  TÌM          hiểu câu hỏi -> ứng viên (BM25 | vector) -> RRF -> rerank -> bỏ trùng -> đóng gói
2  CHỈ MỤC      kb_source · kb_chunk(tsv, embedding, nhãn) · kb_service(tên gọi khác)
1  NẠP          nguồn -> parse -> dựng cấu trúc -> chia đoạn -> gán nhãn + ngữ cảnh -> nhúng -> ghi
```

Quy tắc tách: tầng 3 không biết tool, tầng 4 không biết SQL, tầng 5 là prompt + skill + hook, không có code
riêng. Thêm retriever (graph, SQL danh mục) là thêm một hàm ở tầng 3 trả danh sách có hạng, RRF gộp vào.

Thư mục dự kiến `apps/agent/plugins/knowledge/`:

```
plugin.toml            manifest, user_config (mục 11)
__init__.py            register(ctx): migration, job nạp, tool, prompt section, route, UI
migrations/            SQL có đánh số cho bảng của plugin (mục 4.3)
ingest/                parse_*.py (pdf, docx, xlsx, text), structure.py, chunk.py, enrich.py, embed.py, worker.py
retrieve/              query.py (hiểu câu hỏi), fts.py, vector.py, fuse.py (RRF), rerank.py, pack.py
tools.py               kb_search, kb_read; prompt section "Kho tri thức"
guard.py               hook kiểm số liệu trong câu trả lời (mục 7.4)
routes.py              /v1/plugins/knowledge/...
eval/                  bộ câu hỏi mẫu + lệnh chấm (mục 10)
ui/                    nửa trình duyệt (vite, như Zalo): Nguồn, Dịch vụ, Thử tìm, Cài đặt
```

## 3. Tầng 1: Nạp (ingest)

### 3.1 Nguồn vào

- File: `pdf`, `docx`, `xlsx`, `md`, `txt` (giữ 5 định dạng; chữ ký file kiểm bằng magic bytes, trần dung lượng,
  trần giải nén cho OOXML, như code cũ đã làm vì nó đúng).
- Văn bản gõ tay trên trang quản lý (FAQ ngắn, chính sách).
- *Sau:* "Lấy từ câu trả lời tốt trong Phiên chat" (nhân viên bấm một nút trong trang Phiên chat → thành nguồn
  văn bản chờ duyệt).
- Mỗi nguồn có: tên, loại, định dạng, trạng thái (`cho_xu_ly / dang_xu_ly / san_sang / hong`), số lần thử,
  lỗi đọc được, ngày hiệu lực (cho bảng giá), cờ `approved`, cờ `for_patients` (**theo tài liệu**, user chốt;
  mặc định false), người duyệt + giờ.

### 3.2 Parse và dựng cấu trúc ("sapre" = parse)

Mục tiêu của parse không phải "lấy chữ" mà là ra **một tài liệu Markdown trung gian có tiêu đề đúng**, vì mọi
thứ sau (chia đoạn, nhãn, ngữ cảnh) đều dựa vào tiêu đề.

| Định dạng | Cách | Ghi chú |
|---|---|---|
| DOCX | đọc kiểu đoạn (Heading 1..6) → `#`..`######`; bảng → bảng Markdown nguyên khối | code SAX cũ lấy chữ nhưng bỏ kiểu heading; phải thêm |
| XLSX | mỗi sheet → bảng Markdown; hàng đầu là tiêu đề cột; ô rỗng giữ rỗng | bảng giá: mỗi dòng sau này thành một đoạn (mục 3.3) |
| MD / TXT | dùng nguyên | |
| PDF (có chữ) | **đường Docling** (mục 3.2.1, khuyến nghị): sidecar `docling-serve` trả JSON có thứ bậc tiêu đề, bảng theo ô, thứ tự đọc; **đường đơn giản** (không có sidecar): trích chữ theo trang → dựng cấu trúc 2 lớp: (a) heuristic: lọc đầu/chân trang lặp, dòng IN HOA ngắn = `#`, dòng ngắn ≤ 60 ký tự không có dấu chấm cuối và đứng trước một khối = `##`, dòng bắt đầu bằng `-`/`•`/`‒`/số = mục; (b) **LLM dựng cấu trúc** (bật/tắt được): đưa từng trang cho model, yêu cầu trả lại Markdown với tiêu đề **chép nguyên văn**, không viết lại nội dung; hệ thống so khớp chữ trước/sau (bỏ khoảng trắng) để từ chối nếu model đổi nội dung | heuristic chạy luôn; LLM chỉ khi heuristic tìm được < 3 tiêu đề trên 1.000 ký tự |
| PDF scan (không có chữ) | đường Docling có OCR (EasyOCR/Tesseract có tiếng Việt); đường đơn giản báo "PDF scan, cần OCR" và dừng | |

Kết quả parse được lưu lại (Markdown trung gian + số tiêu đề tìm được) để trang quản lý hiện cho người xem và
sửa tay được trước khi chia đoạn ("Xem bản đã dựng cấu trúc" → sửa → "Nạp lại từ bản này"; "Tách các mục đã
chọn thành nguồn mới" cho cẩm nang trộn phần nội bộ).

#### 3.2.1 Docling (đánh giá, 2026-10-10)

Docling (IBM Research, MIT) đọc PDF/DOCX/PPTX/XLSX/HTML/ảnh ra một `DoclingDocument` thống nhất (JSON không
mất mát, xuất được Markdown): với PDF nó chạy **model phân tích bố cục** (nhận tiêu đề, đoạn, danh sách, chú
thích, thứ tự đọc) và **TableFormer** (cấu trúc bảng theo ô, kể cả ô gộp), OCR tùy chọn (EasyOCR, Tesseract,
RapidOCR; có tiếng Việt), và có cả pipeline VLM nhỏ (Granite-Docling) cho trang khó. Có sẵn `docling-serve`
(FastAPI + Docker image CPU/CUDA) và bộ chia đoạn `HybridChunker` theo thứ bậc.

| | Docling | Đường đơn giản (pypdf/python-docx/openpyxl + heuristic + LLM) |
|---|---|---|
| Tiêu đề trong PDF | từ bố cục trang (font, vị trí) → đúng với PDF sinh từ Word như cẩm nang; **giải đúng phát hiện #1 ở mục 1.2** | đoán theo in hoa/độ dài; hụt với tiêu đề thường; LLM bù nhưng tốn token và phải kiểm |
| Bảng trong PDF | theo ô, giữ ô gộp | pypdf trả chữ chảy dài, bảng mất cột |
| PDF scan | OCR có | không |
| DOCX/XLSX | tốt, cùng một đường | tốt (kiểu heading, ô) |
| Tốn gì | torch + model bố cục/bảng (~vài trăm MB tải lần đầu), RAM 2–4 GB, **CPU vài giây/trang**, GPU nhanh hơn nhiều; thêm một container | không thêm gì; nhanh |
| Tất định | có (không gọi LLM) | heuristic có, LLM không |
| So với MinerU/RAG-Anything | nhẹ hơn, pip cài được, không cần LibreOffice; MinerU mạnh hơn với tài liệu scan phức tạp, tiếng Trung | |

Kết luận: **dùng Docling cho parse, chạy như sidecar `docling-serve`** (giống cầu nối Zalo: container riêng,
agent image không đổi), gọi qua HTTP từ worker nạp; **không nhúng `docling` vào agent** (torch làm image agent
phình và kẹt phiên bản). Cài đặt `parser = docling | simple`; không có sidecar thì tự rơi về `simple` và báo
trên trang Nguồn ("đang đọc PDF bằng cách đơn giản, tiêu đề có thể thiếu"). Bộ chia đoạn vẫn là của plugin
(mục 3.3: cần hàng bảng giá thành đoạn, gộp mục ngắn, tiếng Việt), nhưng ăn JSON `DoclingDocument` thay vì
Markdown trung gian — không phải parse lại Markdown. Với DOCX/XLSX hai đường ngang nhau, Docling chỉ thắng rõ
ở PDF và scan. Việc đầu bước 2: chạy thử Docling trên cẩm nang Nám - Hori và `word-table.docx`, đếm tiêu đề
tìm được so với đường đơn giản, rồi mới chốt mặc định.

### 3.3 Chia đoạn (chunking): có, nhưng theo cấu trúc

Có chia đoạn. Không chia thì bge-m3 nhúng cả cẩm nang 19.500 ký tự thành một vector mờ, và tool trả cả tài
liệu vào ngữ cảnh. Nhưng chia theo **mục**, không theo số ký tự:

1. Đơn vị gốc = một mục (từ tiêu đề này tới tiêu đề kế tiếp cùng cấp hoặc cao hơn). Mỗi đoạn mang **đường
   dẫn tiêu đề** `Tài liệu > TỔNG QUAN > Nguyên nhân`.
2. Mục dài hơn `chunk_max_chars` (mặc định 1.500) thì cắt ở ranh giới tự nhiên (dòng trống > xuống dòng > hết
   câu), đích `chunk_target_chars` 900, chồng lấn 10% **chỉ khi phải cắt trong một mục**. 900 ký tự tiếng Việt
   ≈ 300–350 token bge-m3, đủ một ý trọn vẹn và nhỏ đủ để ghép 5–6 đoạn vào ngân sách tool.
3. Mục ngắn hơn 150 ký tự được **gộp** với mục anh em kế tiếp dưới cùng cha (tránh đoạn "Chỉ định: tất cả các
   dạng nám" đứng một mình).
4. **Bảng:** một bảng ≤ 1.500 ký tự là một đoạn nguyên khối. Bảng dài hơn (bảng giá) → **mỗi hàng một đoạn**,
   hàng ghi dạng "cột: giá trị" kèm tiêu đề bảng, ví dụ `Dịch vụ: Laser CuRAS toàn mặt · Giá: 2.500.000 đ/lần ·
   Gói: 8 lần 16.000.000 đ · Ghi chú: …`. Đây là cách duy nhất để câu "laser bao nhiêu" trúng đúng một hàng.
5. Danh sách gạch đầu dòng dài (hướng dẫn sau điều trị) giữ nguyên trong một đoạn tới mức tối đa, vì tách
   từng gạch đầu dòng làm mất "đây là danh sách việc phải làm".
6. Lọc ký tự ẩn (Unicode Tags) ngay lúc nạp (giữ `tag_ky_tu_an` cũ).

Mỗi đoạn lưu: `ordinal`, `heading_path`, `content` (Markdown), `kind_hint` (text | table | table_row | list),
`page` (PDF), `content_hash` (để bỏ trùng giữa các nguồn), cộng nhãn ở 3.4 và vector ở 3.5.

### 3.4 Gán nhãn và ngữ cảnh (enrichment) bằng LLM: một lượt gọi cho mỗi đoạn

Đây là bước làm cho kho "hiểu dịch vụ" mà không cần đồ thị. Với mỗi đoạn, gửi `heading_path` + nội dung +
tên tài liệu + danh sách dịch vụ đã biết, yêu cầu JSON:

```json
{ "services": ["nam", "bot-hori"],          // mã dịch vụ trong kb_service, hoặc "khac"
  "kind": "aftercare",                      // price | procedure | prep | aftercare | contraindication |
                                            // overview | faq | policy | internal_script | other
  "context": "Hướng dẫn chăm sóc da sau khi bắn laser CuRAS điều trị nám tại Pema." }
```

- `context` (một câu, ≤ 200 ký tự) được **ghép vào trước nội dung khi nhúng** (contextual retrieval) và khi tính
  tsvector, nhưng **không** hiện cho model lúc trả lời (tránh model trích dẫn câu do máy viết). Lý do: đoạn
  "Bôi kem chống nắng 2-3 giờ 1 lần" tự nó không chứa chữ "nám" hay "laser"; có câu ngữ cảnh thì câu hỏi "sau
  laser nám bôi gì" mới trúng.
- Không có nhãn đối tượng theo đoạn (user chốt cờ theo tài liệu, mục 1.2). `kind = internal_script` vẫn được
  gán để trang Chi tiết nguồn **gợi ý** "nguồn này có N mục nội bộ, nên tách" trước khi bật `for_patients`.
- Gọi theo lô: ghép 5–8 đoạn cùng mục vào một lượt để giảm số lượt gọi; trả về mảng JSON; sai định dạng thì
  thử lại một lần rồi ghi `enrich_error`, đoạn vẫn được nhúng **không có nhãn** (tìm vẫn chạy, chỉ kém lọc).
- Model dùng cho bước này: **model chat đang chọn** trên trang Model (user chốt), qua `ctx.model()` (mục 12);
  có cài đặt `enrich_model` để trỏ sang một model khác trong danh sách khi muốn rẻ hơn, mặc định rỗng.
- Chi phí: 5.000 đoạn × ~500 token vào + 80 token ra ≈ 3 triệu token một lần; DeepSeek ≈ 1 USD, Claude Sonnet
  ≈ 10–15 USD; chạy nền, một lần cho mỗi nguồn.

### 3.5 Nhúng (embedding)

- Ollama `bge-m3`, endpoint OpenAI-compatible `POST /v1/embeddings` (client cũ `OllamaEmbeddingClient` chép sang,
  giữ kiểm tra "địa chỉ nội bộ" vì nó bảo vệ đúng thứ cần bảo vệ: câu hỏi bệnh nhân).
- Văn bản nhúng = `heading_path` + `\n` + `context` + `\n` + `content` (cả ba, để vector mang cả vị trí lẫn ý).
- 1024 chiều, chuẩn hóa L2 trước khi ghi, so bằng cosine. Lô 16, timeout 60 s.
- Ghi `embedding_model` và `embedding_dims` vào bảng cài đặt của plugin; vector trả về sai số chiều → từ chối ghi,
  nguồn thành `hong` với lỗi đọc được. Đổi model → nút "Nhúng lại toàn bộ" (job nền, đoạn nào xong ghi đoạn đó,
  tìm vector tạm bỏ qua đoạn chưa có vector của model mới).
- Ollama không chạy: nguồn vẫn nạp xong **không có vector** (trạng thái `san_sang`, cờ `embedded = false`), tìm
  chạy bằng BM25; job nền thử nhúng lại mỗi 5 phút. Không bao giờ để embedding hỏng làm kho tê liệt.

### 3.6 Worker nạp (job nền của plugin)

- `ctx.register_job("ingest")`: vòng 5 s, giành nguồn `cho_xu_ly` bằng `UPDATE … WHERE status = 'cho_xu_ly'
  RETURNING` + `attempts = attempts + 1` ngay trong câu UPDATE (nguồn làm treo worker không bao giờ chạy tới
  nhánh catch), advisory lock để nhiều tiến trình không giẫm nhau.
- Parse chạy trong **tiến trình con** với timeout (mặc định 120 s) và trần RAM; quá hạn thì kill, nguồn `hong`
  với lỗi "đọc file quá lâu". Tối đa 3 lần thử.
- Thứ tự một nguồn: parse → dựng cấu trúc → chia đoạn → ghi đoạn (trạng thái `san_sang`, dùng được ngay bằng
  BM25) → gán nhãn (lô) → nhúng (lô) → cập nhật cờ. Người dùng thấy tiến độ "đã chia 42 đoạn, đang gán nhãn
  18/42, đang nhúng 0/42".
- Nạp lại (reindex) = xóa đoạn cũ của nguồn trong một giao dịch rồi chạy lại; tool tìm trong lúc đó thấy
  nguồn vắng vài giây, chấp nhận được.

## 4. Tầng 2: Chỉ mục và lưu trữ

### 4.1 Bảng (schema `agent_rt`, tiền tố `kb_`)

```
kb_source   id uuid, tenant_id, agent, name, kind(file|text), format, path(data_dir), status, attempts,
            error, structured_md (bản dựng cấu trúc), effective_date, approved bool, approved_by, approved_at,
            for_patients bool, chunk_count, embedded_count, created_at, updated_at
kb_chunk    id bigserial, source_id, ordinal, heading_path text, content text, kind_hint,
            page int, content_hash, services text[], kind text, context text,
            folded text (bỏ dấu của heading+context+content), tsv tsvector GENERATED từ folded,
            embedding vector(1024), embedding_model text, enrich_error text
kb_service  code text, name, aliases text[] ("hori","ota","bớt hori"), description, active
kb_setting  key, value jsonb (embedding_model, dims, …)
```

Không có bảng gán nguồn cho từng agent: một profile agent dùng một kho. Nếu sau này nhiều agent dùng chung một
Postgres thì khóa `(tenant_id, agent)` đã có trên `kb_source` để tách.

### 4.2 Index

- `GIN (tsv)` — BM25 tính ở tầng ứng dụng trên ứng viên (giữ cách cũ: `to_tsquery` OR các lexeme, config
  `simple`, chữ đã bỏ dấu; Postgres không có BM25, `ts_rank` thiếu IDF).
- `HNSW (embedding vector_cosine_ops)` — với kho nghìn đoạn thì quét đúng (`+ 0` tắt index) vẫn nhanh, index để
  dành khi kho lớn; lọc theo nhãn và audience **trong WHERE trước khi xếp hạng**.
- `btree (source_id, ordinal)`, `GIN (services)`, `btree (kind)`; đối tượng và duyệt lọc qua JOIN `kb_source`.
- Tiếng Việt: bỏ dấu bằng hàm riêng (xử lý `đ`) **trước** khi ghi `folded`, cùng một hàm cho câu hỏi. Giữ.

### 4.3 Migration của plugin (bổ sung ở lõi)

Plugin hiện chỉ có `ctx.storage` (JSON). Thêm `ctx.register_migrations(folder)`: thư mục `migrations/0001_*.sql`
… do plugin sở hữu, bảng phiên bản `agent_rt.plugin_migration(plugin, version)`. Chạy bởi `agent db migrate`
(cùng lúc với alembic của agent, dùng `AGENT_MIGRATION_DATABASE_URL` là role chủ) — **không** để plugin tự chạy
DDL khi bật, vì service chạy bằng role `agent_rt_app` không có quyền DDL và không nên có. Bật plugin mà migration
chưa chạy → plugin báo lỗi rõ "chạy `agent db migrate`" thay vì chết lặng. Grant SELECT/INSERT/UPDATE/DELETE cho
`agent_rt_app` nằm trong script.

## 5. Tầng 3: Tìm (retrieval)

### 5.1 Hiểu câu hỏi (không gọi LLM, < 1 ms)

- Bỏ dấu, tách từ (cùng hàm với lúc ghi).
- **Mở rộng tên gọi dịch vụ** từ `kb_service.aliases`: "hori" → thêm "bot hori", "ota"; đồng thời suy ra bộ lọc
  `services` nếu tool không được truyền.
- Nhận ra số tiền, số lần, đơn vị ("2 triệu", "8 buổi") để ưu tiên đoạn `kind = price/procedure`.
- Câu quá ngắn hoặc không còn từ nào sau khi lọc → tool trả "câu hỏi chưa đủ để tra, hỏi lại người dùng".

### 5.2 Ứng viên: hai danh sách song song, lọc trong SQL

Cả hai nhánh đều có cùng mệnh đề WHERE (JOIN `kb_source`): nguồn `san_sang`, `approved` và `for_patients` theo
kênh (mục 6.3), nhãn `services`/`kind` nếu được truyền.

- **BM25**: `tsv @@ to_tsquery(...)` lấy tối đa 2.000 ứng viên, tính BM25 (k1 = 1.2, b = 0.75, IDF trên các
  đoạn được phép đọc), lấy `3 × k`.
- **Vector**: nhúng câu hỏi (cùng model), cosine distance ≤ ngưỡng (`vector_max_distance`, mặc định 0.6, **phải
  đo lại** trên bge-m3 với dữ liệu thật, mục 10), lấy `3 × k`. Ollama lỗi → danh sách rỗng, không ném lỗi.
- Nếu người dùng truyền bộ lọc mà không có kết quả → tự nới lỏng một lần (bỏ `kind`, rồi bỏ `services`) và
  đánh dấu "đã nới lọc" trong kết quả để agent biết.

### 5.3 Gộp: RRF

`score = Σ 1/(k + rank)`, k = 60, lấy top 20. Giữ hàm `hop_nhat_rrf` cũ (thuần, có test).

### 5.4 Rerank: bật mặc định, có đường lùi

- **Bản đầu:** rerank **listwise bằng LLM** (**model chat đang chọn**, user chốt; `rerank_model` để trỏ model
  khác khi muốn):
  gửi câu hỏi + 20 ứng viên rút gọn (heading_path + 300 ký tự đầu), yêu cầu trả JSON `[{id, score 0-3}]`.
  Điểm cuối = 0.7 × rerank + 0.3 × RRF chuẩn hóa (để một ứng viên rerank chấm 0 nhưng RRF rất cao không rớt
  hẳn). ~1.500 token/lượt, 1–2 s. Timeout 8 s hoặc JSON hỏng → dùng thứ tự RRF.
- **Bước 2:** cross-encoder cục bộ `bge-reranker-v2-m3` (Ollama không phục vụ reranker; cần container
  `text-embeddings-inference` hoặc `infinity`, ~1 GB VRAM). Bật qua cài đặt `rerank_backend = llm | local | off`.
- Rerank có tắt được: với bộ câu hỏi đo, so `off` vs `llm` để biết nó mua được bao nhiêu.

### 5.5 Bỏ trùng và đa dạng

- Bỏ trùng theo `content_hash` (hai nguồn chép nguyên nhau giữ một, ưu tiên nguồn mới/đã duyệt).
- Tối đa 2 đoạn liền kề của cùng một mục, trừ khi `kind = procedure` (quy trình nhiều bước thì cho tới 4).
- Kết quả cuối k = 5 (`top_k`, 1–20).

### 5.6 Đóng gói kết quả cho model

```
[Nguồn 1: Cẩm nang điều trị Nám - Hori › NỘI DUNG › Hướng dẫn sau điều trị | dịch vụ: nám, bớt Hori | cập nhật 03/2026]
- Bôi kem tái tạo da, kem đặc trị sắc tố hàng ngày theo chỉ định.
- Bôi kem chống nắng 2-3 giờ 1 lần …

[Nguồn 2: Bảng giá 2026 › Laser › hàng 7 | dịch vụ: nám | hiệu lực 01/01/2026]
Dịch vụ: Laser CuRAS toàn mặt · Giá: 2.500.000 đ/lần · Gói: …
```

- Ngân sách `max_result_chars` (mặc định 6.000) cho **cả chuỗi**; đoạn không vừa thì bỏ hẳn, không cắt cụt.
- Nội dung đoạn đi qua bộ lọc **chống giả nhãn** (một tài liệu tự viết `[Nguồn: …]` để gán nội dung cho nguồn
  khác) và bộ lọc ký tự ẩn (giữ code cũ, nó giải đúng một lỗ hổng thật).
- Toàn bộ kết quả được bọc là **nội dung không tin cậy** (hook `result_warning` sẵn có của lõi + thẻ
  `<kb-results>` để model phân biệt dữ liệu với chỉ dẫn).
- Không có kết quả qua ngưỡng → tool trả `is_error = false` nhưng nội dung là câu cố định: "Không có nội dung
  nào trong kho tri thức khớp '…'. Nói thật với người hỏi là tài liệu chưa có, không bịa số liệu."

## 6. Tầng 4: Công cụ cho agent

### 6.1 `kb_search`

```
kb_search(query: str, services?: list[str], kind?: enum, k?: int=5)  read_only, timeout 15 s
```
Mô tả tool (phần model đọc để quyết định gọi): "Tra tài liệu của phòng khám: giá, liệu trình, quy trình, chuẩn
bị, chăm sóc sau, chống chỉ định, chính sách. GỌI TRƯỚC khi trả lời bất kỳ câu nào về dịch vụ của phòng khám;
không trả lời bằng kiến thức chung khi có tool này. Truyền `services` khi đã biết dịch vụ, `kind` khi biết
người hỏi cần gì. Kết quả kèm tên nguồn để dẫn lại."

### 6.2 `kb_read`

```
kb_read(source_id: str, heading_path?: str)  read_only
```
Trả **trọn một mục** (tới 4.000 ký tự) khi đoạn tìm được là một phần của quy trình dài, hoặc mục lục của tài
liệu khi không truyền `heading_path`. Chỉ đọc được đoạn cùng audience/approval với `kb_search`.

### 6.3 Ai thấy gì: quyết bởi kênh, không bởi model

- `ToolContext.channel` do lõi đặt từ kênh của lượt chat (`zalo-<account>`, `http`, `cli`), model không sửa được.
- Cài đặt `patient_channel_prefixes` (mặc định `["zalo-"]`): kênh khớp = **kênh bệnh nhân** → chỉ đoạn của
  nguồn `for_patients = true AND approved = true`. Kênh khác = nhân viên → thấy tất cả, kể cả nguồn chưa duyệt
  (có đánh dấu "chưa duyệt" trong kết quả để nhân viên biết).
- Đây là một mệnh đề WHERE, không phải prompt. Nguồn nội bộ không bao giờ ra kênh bệnh nhân dù model có "xin".

### 6.4 Tool chỉ xuất hiện khi có gì để tra

Như zalo-agent: không có nguồn `san_sang` nào thì không đăng ký tool (bày một tool luôn trả rỗng chỉ dạy
model gọi vô ích). Job nền của plugin đăng ký/gỡ tool khi số nguồn sẵn sàng đổi (cơ chế `register_tool` +
disposer đã có; Zalo làm tương tự với channel).

### 6.5 Prompt section "Kho tri thức" (session, ngắn, ít đổi)

```
## Kho tri thức
Bạn có tool kb_search/kb_read. Kho đang có N tài liệu về các dịch vụ: nám (bớt Hori, laser CuRAS), mụn, …;
loại nội dung: giá, liệu trình, quy trình, chăm sóc sau, chống chỉ định, chính sách.
Cách dùng: <thủ tục ở mục 7.1, 6–8 dòng>.
```
Danh sách dịch vụ lấy từ `kb_service` lúc dựng system prompt (đóng băng theo phiên; đổi danh mục thì phiên
sau mới thấy, chấp nhận được).

## 7. Tầng 5: Điều khiển (phần "agentic")

### 7.1 Thủ tục agent làm theo (nằm trong prompt section + skill `tra-cuu-tai-lieu`)

1. Nhận diện **dịch vụ** người hỏi nói tới (dùng tên gọi khác trong danh sách) và **loại** câu hỏi.
2. `kb_search` với `services`/`kind` đã nhận diện; **truy vấn phải tự đứng được**: câu nối tiếp ("thế còn giá?")
   phải thành "giá laser CuRAS điều trị nám", không gửi đại từ.
3. Đọc kết quả, tự hỏi: *đã có đúng con số / đúng bước cần trả lời chưa?*
   - thiếu → tìm lại: bỏ bộ lọc, đổi cách gọi, hoặc `kb_read` trọn mục; **tối đa 3 lượt tìm** một lượt trả lời;
   - câu hỏi hai ý (mang thai + laser) → hai lượt tìm, mỗi lượt một ý, rồi ghép.
4. Trả lời: **số liệu chép nguyên văn** (không làm tròn, không quy đổi), nêu nguồn ngắn gọn ("theo cẩm nang
   điều trị nám"), không nhắc mục nội bộ, không dán nguyên đoạn.
5. Không có trong tài liệu → nói rõ "tài liệu hiện chưa có thông tin này", đề nghị đặt lịch tư vấn; **không
   đoán**.
6. Ranh giới (giữ trong AGENTS.md của profile, không phải của plugin): không chẩn đoán, không hứa kết quả, không
   tự quyết giá ngoài bảng → chuyển bác sĩ/nhân viên.

### 7.2 Thông số vòng lặp

Profile `clinic`: `max_steps` 6 → **10** (3 lượt tìm + 1 đọc + trả lời vẫn dư). Guard chống lặp sẵn có
(`repeat_thresholds`) chặn việc gọi `kb_search` cùng tham số nhiều lần.

### 7.3 Multi-hop không cần đồ thị

"Đang bôi retinol có làm laser được không": lượt 1 `kb_search(services=[laser], kind=contraindication)`, lượt 2
nếu cần `kb_search("retinol ngưng bao lâu trước laser")`. Nhãn `services` + `kind` làm việc của cạnh đồ thị.
Khi bộ đo (mục 10) cho thấy câu nối nhiều dịch vụ còn hụt, lúc đó thêm retriever graph ở tầng 3.

### 7.4 Hook kiểm số liệu (citation guard) — bước 2

`PostModelHook` của plugin: trước khi gửi câu trả lời, lấy mọi số tiền/số lần/thời gian trong câu trả lời
(regex), kiểm xem chúng có xuất hiện trong các đoạn tool đã trả trong lượt này không. Không có → viết lại một
lần với ghi chú "con số X không có trong tài liệu, bỏ hoặc nói rõ là ước lượng". Rẻ (không gọi LLM thêm trừ khi
phải viết lại), chặn đúng lỗi đáng sợ nhất của RAG phòng khám: **bịa giá**.

## 8. An toàn và quyền (thiết kế mới, giữ cái đúng)

| Rủi ro | Cách chặn |
|---|---|
| Nội dung nội bộ lọt ra bệnh nhân | cờ `for_patients` theo **tài liệu** (mặc định false), lọc theo kênh trong SQL (6.3); cẩm nang trộn thì tách nguồn; `kind = internal_script` gợi ý tách |
| Tài liệu chưa ai xem đã được trích | cờ `approved` theo nguồn; kênh bệnh nhân chỉ thấy nguồn đã duyệt; ai duyệt: bất kỳ admin (owner/manager), ghi tên + giờ. Không cần vai bác sĩ trong agent; muốn bác sĩ ký thì làm ngoài hệ thống rồi admin bấm |
| Dữ liệu bệnh nhân vào kho | trang Thêm cảnh báo; quét số điện thoại/CCCD khi nạp → cảnh báo (không chặn) |
| Prompt injection trong tài liệu | bọc không tin cậy, chống giả nhãn nguồn, lọc ký tự ẩn, `read_only` tool |
| File độc | magic bytes, trần dung lượng/giải nén, parse trong tiến trình con có timeout + trần RAM, 3 lần thử |
| Bịa số | hook 7.4, thủ tục 7.1 bước 4 |
| Câu hỏi bệnh nhân rời máy | embedding cục bộ; kiểm "địa chỉ nội bộ" trên endpoint embedding |

## 9. Giao diện quản lý (nửa trình duyệt của plugin, như Zalo)

Tab trong trang plugin `knowledge` của "Điều khiển agent":

1. **Nguồn**: bảng (tên, dịch vụ, loại, trạng thái + tiến độ, đoạn, đã duyệt, cho bệnh nhân, cập nhật), lọc,
   tìm; nút Thêm (file / văn bản), Nạp lại, Duyệt/Bỏ duyệt, Xóa (hỏi lại, nói rõ số đoạn mất).
2. **Chi tiết nguồn**: bản dựng cấu trúc (sửa được → nạp lại từ bản này; "Tách các mục đã chọn thành nguồn
   mới"); danh sách đoạn với nhãn `services / kind` **sửa được từng đoạn**; cờ `for_patients`, `approved` của
   nguồn; cảnh báo "có N mục nội bộ" khi bật cho bệnh nhân; lỗi nạp đọc được.
3. **Dịch vụ**: mã, tên, tên gọi khác, mô tả; số đoạn mỗi dịch vụ. Đây là "xương sống" của kho.
4. **Thử tìm**: nhập câu hỏi, chọn "như kênh bệnh nhân / như nhân viên", hiện **từng tầng**: ứng viên BM25,
   ứng viên vector (với khoảng cách), sau RRF, sau rerank, gói cuối đúng như model thấy, thời gian từng bước.
   Trang này là công cụ chỉnh tham số, không phải trang trình diễn.
5. **Cài đặt**: parser (`docling` sidecar: địa chỉ, trạng thái | `simple`), embedding (địa chỉ, model, trạng thái
   Ollama, nút "Nhúng lại"), enrich (bật/tắt, model), rerank (off/llm/local, model), `top_k`, `rrf_k`,
   `vector_max_distance`, `max_result_chars`, `chunk_target/max`, `patient_channel_prefixes`, "chỉ nguồn đã
   duyệt cho kênh bệnh nhân" (mặc định bật).

Tab "Hiểu biết" (5 tầng, làm sau) sẽ có mục "Tài liệu" dẫn sang đây.

## 10. Đo lường: có ngay từ bước 1

- `eval/questions.jsonl`: 50–100 câu **lấy từ Phiên chat Zalo thật** (trang Phiên chat đã có) + nhân viên ghi:
  `{"q": "...", "channel": "patient|staff", "expect_sources": ["..."], "expect_facts": ["2.500.000", "8-10 lần"],
  "expect_refuse": false, "hops": 1}`. Có đủ các nhóm ở 1.1, có ~15% câu multi-hop, ~10% câu phải từ chối.
- Lệnh `agent kb eval [--no-rerank] [--no-vector]` (route admin + CLI): chạy **tầng 3** (không chạy agent) và
  chấm: `hit@5` theo nguồn, **tỉ lệ fact có mặt trong gói kết quả**, độ trễ, token rerank. Chạy thêm chế độ
  "end-to-end" gọi cả agent và chấm câu trả lời bằng rubric (fact đúng, từ chối đúng, không lộ nội bộ).
- So ba cấu hình: BM25 → +vector → +rerank. Lưu kết quả vào `eval/results/<ngày>.json`, commit, để thấy tiến
  bộ hay thụt lùi khi đổi tham số (ngưỡng 0.6, k, chunk size).
- Hiệu chuẩn `vector_max_distance` trên bộ này trước khi bật mặc định.

## 11. Cấu hình plugin (`plugin.toml` `user_config`)

`parser` (docling|simple, mặc định docling, tự rơi về simple khi sidecar vắng), `docling_url`
(`http://docling:5001`), `embedding_base_url` (mặc định `http://host.docker.internal:11434/v1` cho dev,
`http://ollama:11434/v1` compose), `embedding_model` (bge-m3), `enrich_enabled`, `enrich_model` (entry của danh
sách model; rỗng = model chat đang chọn), `rerank_backend` (off|llm|local), `rerank_model` (rỗng = model chat),
`top_k` 5, `rrf_k` 60, `vector_max_distance` 0.6, `max_result_chars` 6000, `chunk_target_chars` 900,
`chunk_max_chars` 1500, `patient_channel_prefixes` ["zalo-"], `require_approval_for_patients` true, `max_file_mb`
25, `extract_timeout_s` 120.

## 12. Những gì lõi (`agent_app`/`agentcore`) phải thêm

1. `ctx.register_migrations(folder)` (mục 4.3) — bắt buộc.
2. `ctx.model(entry_id: str | None = None) -> ModelClient` — để enrich/rerank dùng model của danh sách model vừa
   làm, qua `DynamicModel`/`ModelAdmin`, không để plugin tự cầm key. Nhỏ. **User đồng ý 2026-10-10.**
3. Đăng ký/gỡ tool lúc chạy: đã kiểm — `register_tool` + disposer làm `Live` dựng lại assembly (`live.current()`),
   lượt kế tiếp thấy bộ tool mới. Không cần đổi.
4. Hook `PostModelHook(run: (AssistantResult, HookContext) -> AssistantResult)` đã có; 7.4 dùng được ngay
   (hook sửa/ghi chú câu trả lời; muốn model viết lại thì gọi `ctx.model()` trong hook).
5. Trace của tool: lõi ghi `detail = {call_id, result_chars, blocked_by}` cố định (`run_turn._tool_event`).
   **Cần thêm (nhỏ):** `ToolOutput.detail: dict` được chép vào `TraceEvent.detail`, để `kb_search` ghi số ứng
   viên, rerank, nới lọc, độ khớp cao nhất (mục 17.3).
6. Nén hội thoại: đã kiểm — prompt nén của lõi yêu cầu "giữ tên, số, ngày, mã định danh, không bịa", nên số
   liệu đã trích được giữ; tên nguồn là định danh nên cũng được giữ. Không cần đổi; bộ đo end-to-end có một
   ca "hỏi sau khi nén".
7. Skill: plugin chưa đăng ký được skill (skill bundled nằm trong thư mục profile). Thủ tục 7.1 đi bằng prompt
   section của plugin; `register_skill` là việc sau nếu thấy cần.
8. CLI: plugin chưa thêm được lệnh `agent …`; `kb eval` là route admin + script nhỏ gọi route.
9. Profile `clinic`: `max_steps = 10`, `plugins.enabled` thêm `knowledge`.

## 13. Hạ tầng

- **Dev (Windows, RTX 3060):** cài Ollama bản Windows chạy trực tiếp trên máy (đơn giản hơn GPU trong Docker
  Desktop), `ollama pull bge-m3`; agent trong compose trỏ `http://host.docker.internal:11434/v1`. VRAM ~1,2 GB.
- **Máy chủ:** mở lại service `ollama` trong `infra/docker-compose.yml` (đang comment), profile `ollama`; không có
  GPU thì bge-m3 chạy CPU vẫn được cho kho này (~200 ms/câu hỏi, nạp 5.000 đoạn ~10 phút); hoặc chuyển
  `embedding_base_url` sang API (Gemini, cắt 1024) rồi "Nhúng lại".
- Bước 2 nếu rerank cục bộ: thêm container `text-embeddings-inference` với `bge-reranker-v2-m3`.
- **Docling sidecar** (bước 2): service `docling` trong compose từ image `docling-serve` (bản CPU đủ cho PDF
  sinh từ Word; bản CUDA khi có GPU), chỉ `expose` trong mạng compose, volume cache model; healthcheck. Dev
  Windows: chạy cùng image đó bằng Docker, agent trỏ `http://docling:5001` (hoặc host.docker.internal nếu chạy
  ngoài compose).

## 14. Thứ tự làm (mỗi bước một commit, dùng được sau mỗi bước)

| Bước | Nội dung | Dùng được gì sau bước này |
|---|---|---|
| 0 | Lõi: `register_migrations`, `ctx.model`; `max_steps` 10 | nền |
| 1 | Bảng + nạp `md/txt/docx/xlsx` (đường đơn giản: kiểu heading + bảng), chia đoạn theo mục, BM25, `kb_search`, prompt section, cờ `for_patients`/`approved` + lọc theo kênh, route + trang Nguồn tối thiểu, `eval` với 30 câu | tra được bảng giá và FAQ gõ tay, an toàn để bật trên Zalo, có số đo baseline |
| 2 | PDF: spike Docling trên cẩm nang thật → sidecar `docling-serve` + đường đơn giản (heuristic + LLM) làm dự phòng; trang Chi tiết nguồn (sửa bản dựng, tách mục thành nguồn mới, nhãn) | nạp được cẩm nang thật |
| 3 | Enrich (nhãn dịch vụ/loại + ngữ cảnh) bằng model chat, `kb_service` + tên gọi khác, gợi ý tách mục nội bộ | tìm có lọc theo dịch vụ |
| 4 | Embedding bge-m3 + vector + RRF, hiệu chuẩn ngưỡng, nút Nhúng lại; trang Thử tìm theo tầng | hybrid |
| 5 | Rerank LLM (độ khớp hiện trong kết quả tool), `kb_read`, skill `tra-cuu-tai-lieu`, hook kiểm số liệu, nhật ký câu hỏi hụt `kb_gap` + trang "Câu hỏi chưa có tài liệu" | agentic đầy đủ, vòng phản hồi |
| 6 | Chuyển các nguồn `guide` của clinic API thành nguồn `for_patients = false` của plugin (công cụ chuyển một lần), bỏ `/guide` và `apps/api/pema/knowledge` + `admin_kb.py` + bảng `agent.kb_*` (**user chốt 2026-10-10**); lấy nguồn từ Phiên chat + đánh dấu câu trả lời sai → bộ đo; nguồn thay thế nguồn (hiệu lực); rerank cục bộ (tùy) | clinic API không còn RAG |

## 15. Không làm (và khi nào xem lại)

- Graph RAG: khi bộ đo cho thấy câu nối ≥ 2 dịch vụ hụt dù agent đã tìm 3 lượt.
- Đa phương thức (ảnh trước/sau, sơ đồ): khi có tài liệu như vậy thật; lúc đó spike RAG-Anything/Docling ở
  container riêng.
- Doris / vector DB riêng: khi kho vượt vài trăm nghìn đoạn hoặc có kho phân tích chung.
- Nhiều agent chung một kho với quyền khác nhau: khi có agent thứ hai.

## 16. Câu hỏi đã được user trả lời (2026-10-10)

1. Đối tượng (bệnh nhân / nội bộ): **cờ theo tài liệu** (`for_patients`), không nhãn theo đoạn. Cẩm nang
   trộn → tách nguồn (mục 1.2, 3.2).
2. Model cho enrich/rerank: **model chat đang chọn** (cài đặt ghi đè để trống).
3. `ctx.model` trong lõi: **đồng ý**.
4. `/guide` của clinic: **chuyển thành nguồn nội bộ (`for_patients = false`) trong plugin rồi bỏ `/guide`**
   (bước 6).

Còn mở: chọn Docling làm parser mặc định hay chỉ dự phòng — quyết sau spike ở đầu bước 2 (mục 3.2.1).

## 17. Bản đồ đầy đủ một hệ Agentic RAG: chỗ của từng phần (bổ sung 2026-10-10)

Mục 1–16 tập trung vào nạp → tìm → tool. Một hệ Agentic RAG còn các phần quanh vòng lặp dưới đây. Cột
"Ở đâu": **lõi** = `agentcore`/`agent_app` đã có, **plan §n** = đã nằm trong plan, **bổ sung** = thêm hôm nay,
**sau** = cố ý chưa làm.

### 17.1 Trước khi tìm (phía câu hỏi)

| Phần | Cách xử lý | Ở đâu |
|---|---|---|
| Định tuyến: có cần tra không (chào hỏi, đặt lịch, than phiền thì không) | Trong agentic RAG người định tuyến là **model**, qua mô tả tool và prompt section; không có bộ phân loại riêng. Khi có plugin khác (đặt lịch, CRM) thì mỗi plugin thêm tool, model chọn | plan §6.1, §6.5 |
| Câu hỏi nối tiếp ("thế còn giá?", "cái đó mấy buổi?") | Model tự viết truy vấn **đầy đủ** từ hội thoại (thay đại từ bằng tên dịch vụ) — lợi thế của agentic so với pipeline RAG, không cần bộ viết lại riêng. Ghi rõ trong thủ tục 7.1: "truy vấn phải tự đứng được, có tên dịch vụ" | bổ sung vào §7.1 |
| Tách câu hỏi nhiều ý, multi-query | Model tách và gọi nhiều lượt (§7.3). Không làm HyDE/multi-query tự động: hybrid + rerank + 3 lượt tìm đã phủ; thêm bước sinh truy vấn giả chỉ tốn token | plan §7.3 |
| Chuẩn hóa tên gọi, lỗi chính tả, không dấu | Bỏ dấu + tên gọi khác từ `kb_service`; bge-m3 chịu được lỗi chính tả nhẹ; trie fuzzy để sau nếu bộ đo cho thấy cần | plan §5.1 |
| Cache | Cache vector câu hỏi (LRU 1.000, theo chuỗi đã chuẩn hóa) và cache kết quả `(query, bộ lọc, kênh)` trong 5 phút để câu lặp của nhiều bệnh nhân không chạy rerank lại; system prompt đã được lõi đóng băng theo phiên nên tool results không phá prompt cache của nhà cung cấp | bổ sung §5 |
| Kẹp đầu vào | `query` ≤ 500 ký tự, `k` 1–20, `services` ≤ 5; tool `read_only`, timeout 15 s | bổ sung §6.1 |

### 17.2 Sau khi tìm (phía câu trả lời)

| Phần | Cách xử lý | Ở đâu |
|---|---|---|
| Chấm kết quả tìm (kiểu CRAG: đủ / thiếu / sai) | Hai lớp: (a) tool trả kèm **độ khớp** của rerank cho từng đoạn (`cao/vừa/thấp`) và cờ "đã nới lọc"; dưới ngưỡng thì tool nói thẳng "kết quả yếu"; (b) model đọc và tự quyết tìm lại (§7.1 bước 3). Không có bộ chấm LLM riêng: rerank đã là bộ chấm | bổ sung §5.4/§5.6 |
| Tổng hợp có dẫn nguồn | Thủ tục 7.1 bước 4; nguồn là tên tài liệu, không phải id | plan §7.1 |
| Kiểm chứng sau sinh (bịa số) | Hook kiểm số liệu `PostModelHook`: mọi con số trong câu trả lời phải có trong đoạn đã tìm, không thì viết lại | plan §7.4 |
| Từ chối / độ tin cậy | "Tài liệu chưa có" là câu cố định từ tool; ranh giới y khoa ở AGENTS.md; không cho model tự chấm điểm tin cậy bằng số (vô nghĩa) | plan §5.6, §7.1 |
| Chuyển người thật | Ngoài phạm vi plugin RAG: cần cơ chế "tag nhân viên / tạm dừng agent trên hội thoại" ở tầng kênh (Zalo) hoặc plugin cổng phê duyệt đã ghi trong handoff. RAG chỉ cần nói "để em chuyển bạn cho nhân viên" khi gặp ranh giới | sau (plugin riêng) |
| Trả lời dạng stream | Lõi có `StreamSink`; tool chạy trước, câu trả lời cuối stream như thường | lõi |

### 17.3 Vòng ngoài (vận hành và học)

| Phần | Cách xử lý | Ở đâu |
|---|---|---|
| Quan sát (observability) | Lõi ghi mỗi lượt gọi tool vào trace (tên, thời gian, lỗi, kích thước). Bổ sung: `kb_search` ghi `detail` = số ứng viên BM25/vector, có rerank không, đã nới lọc, top độ khớp → trang Trace hiện, và "Thử tìm" có nút "chạy lại truy vấn này" từ một trace | lõi + bổ sung §9.4 |
| Số đo vận hành | Từ trace: % lượt có gọi `kb_search`, % lượt tool trả rỗng, số lượt tìm trung bình/lượt trả lời, thời gian rerank → thẻ trên Tổng quan (sau) | sau (dùng dữ liệu đã có) |
| **Nhật ký câu hỏi hụt** (`kb_gap`) | Mỗi lần tool trả rỗng/yếu: ghi (câu hỏi đã chuẩn hóa, kênh, ngày, đếm). Trang "Câu hỏi chưa có tài liệu" xếp theo số lần → nhân viên bấm "Viết câu trả lời" → thành nguồn văn bản. Đây là vòng phản hồi rẻ nhất và đáng nhất | bổ sung, bước 5 |
| Phản hồi của nhân viên | Trang Phiên chat: đánh dấu một câu trả lời "sai/đúng" → ghi thành ca trong bộ đo (`eval/questions.jsonl` + câu trả lời mong muốn) | bổ sung, bước 6 |
| Đánh giá offline | Bộ đo + `agent kb eval`, so BM25 / +vector / +rerank, commit kết quả | plan §10 |
| Tươi mới của dữ liệu | `effective_date` + `expires_at` trên nguồn; nguồn mới có thể **thay thế** nguồn cũ (`supersedes`), nguồn bị thay thành `het_hieu_luc` (không tìm, còn xem); tool ưu tiên nguồn có hiệu lực và ghi ngày trong nhãn nguồn; nhắc trên trang Nguồn khi bảng giá quá 12 tháng | bổ sung §3.1, bước 6 |
| Nạp lại khi tài liệu đổi | Tải lại = phiên bản mới của cùng nguồn (giữ id, nhãn đã sửa tay được giữ theo `heading_path` khi khớp), đoạn sinh lại trong một giao dịch | plan §3.6 + bổ sung |
| Bộ nhớ hội thoại và nén | Lõi: kết quả tool nằm trong hội thoại tới khi nén; cần kiểm tra prompt nén của lõi **giữ số liệu đã trích kèm tên nguồn** (nếu không, sau nén model có thể hỏi lại hoặc bịa). Việc của lõi, ghi vào handoff | lõi (kiểm) |
| Bộ nhớ dài hạn vs RAG | Tách bạch: ghi chú về người → memory; tri thức → RAG. Không cho memory tool lưu nội dung tài liệu | plan (nguyên tắc) |
| Nhiều nguồn dữ liệu (catalog, lịch, CRM) | Mỗi thứ là một plugin với tool riêng; agent là bộ định tuyến; RAG không gọi SQL của người khác. `kb_service` là catalog tối thiểu tới khi có plugin `clinic_*` | sau (clinic_*) |
| Chi phí / độ trễ mỗi lượt | Ngân sách: ≤ 3 lượt tìm; rerank chỉ khi > k ứng viên; cache 5 phút; nhúng câu hỏi ~20 ms, SQL ~50 ms, rerank 1–2 s → lượt trả lời có tra cứu thêm ~2–4 s so với không tra | bổ sung |
| Đa tenant / nhiều agent | Khóa `(tenant_id, agent)` trên mọi bảng; một kho mỗi agent; chia sẻ kho giữa agent là việc sau | plan §4.1 |
| An toàn | §8 | plan §8 |
| Bác sĩ duyệt câu trả lời (human-in-the-loop) | Không phải việc của RAG; plugin cổng phê duyệt (handoff "Câu hỏi còn mở") | sau |

Những thứ cố ý **không** có: bộ viết lại truy vấn riêng, HyDE, bộ chấm LLM riêng cho kết quả, điểm tin cậy
bằng số, Graph RAG, đa phương thức. Lý do chung: trong agentic RAG, model đã làm việc định tuyến, viết lại và
tự chấm; thêm một tầng LLM nữa là tốn token cho việc model đang làm. Mỗi thứ trên có đường quay lại khi bộ đo
chỉ ra lỗ hổng cụ thể.
