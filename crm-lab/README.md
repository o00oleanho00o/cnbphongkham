# crm-lab — sân thử ý tưởng CRM

Đây là **bản chép** của web Pema cũ (`prototype/`) để thử ý tưởng CRM thoải mái: sửa HTML, JS, CSS tùy ý.
Bản gốc `prototype/` không được sửa, vì thiết kế web (gói W) và bảng đối chiếu (gói U) đo theo nó.

Ý tưởng nào làm ở đây thì ghi lại trong `crm-ideas/<tên-ý-tưởng>/` (xem `crm-ideas/README.md`). Người phụ trách hệ
mới (Python + Next.js) đọc ở đó rồi quyết cách đưa sang.

## Chạy

Từ thư mục gốc của repo, mở hai cửa sổ:

```powershell
python -m http.server 4177 --bind 127.0.0.1 --directory crm-lab
python crm-lab/finance_server.py
```

- Web phòng khám: http://127.0.0.1:4177/clinic-web/
- Web bệnh nhân: http://127.0.0.1:4177/patient-mobile/
- Đổi tài khoản demo bằng ô "Tài khoản demo" trên đầu trang, hoặc thêm `?staff=owner-tam` / `doctor-mai` / `care-maianh` / `accountant` vào địa chỉ.
- Tài chính chạy cổng 4176 và dùng file dữ liệu riêng `.local/crm-lab-finance.sqlite3`, không đụng web cũ (4173/4174).
- Dữ liệu demo nằm trong localStorage của trình duyệt theo cổng 4177; nút ↻ trên đầu trang đặt lại về dữ liệu mẫu.

## Chụp màn

```powershell
node crm-lab/tools/shot.cjs --url "http://127.0.0.1:4177/clinic-web/?staff=owner-tam" --click ".sidebar [data-nav=\"crm\"]" --out crm-ideas/<tên>/shots/sau-crm
```

Cần Playwright một lần: `cd pema-agent/frontend; pnpm install; npx playwright install chromium`.
Mặc định chụp 1440×900 và 390×844. Muốn chụp "trước" thì chạy web cũ (`python -m http.server 4173 --bind 127.0.0.1 --directory prototype`) và đổi cổng trong `--url`.

## Có gì ở đây

| Thư mục | Nội dung |
|---|---|
| `clinic-web/` | Trang web phòng khám (một file, nạp script từ `shared/`) |
| `patient-mobile/` | Web bệnh nhân |
| `shared/` | Toàn bộ logic và giao diện dùng chung: `crm-*.js` (CRM), `clinic.js`, `data.js`, `operations-*.js` (lịch), `order-*.js` (đơn), `care-finance.js`, `design.css` |
| `finance/`, `finance_server.py` | Màn tài chính và máy chủ tài chính (SQLite) |
| `order-review/` | Phiếu đơn A5 |
| `tools/shot.cjs` | Công cụ chụp màn |

Dữ liệu chỉ là giả lập. Không đưa dữ liệu bệnh nhân thật, số điện thoại thật hay ảnh thật vào đây.
