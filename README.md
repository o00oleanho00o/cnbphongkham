# Contete Agent

Một agent trả lời từ kho tri thức của chính nó (agentic RAG), trên khung chat web và trên các nền tảng chat mà connector
mang tới (Zalo). Gồm: lõi harness, các plugin, động cơ ca cho tin chủ động, và một dashboard cho nhân viên.

## Chạy

Cần Docker. Từ thư mục gốc của repo, với giá trị demo (cổng chỉ mở ở 127.0.0.1):

    docker compose up --build

Mở http://localhost:3000. Lần đăng nhập đầu tiên tạo tài khoản quản trị của agent. Khóa API của model đặt trên dashboard.

Cài thật (file `infra/.env` với mật khẩu ngẫu nhiên, Caddy, sao lưu): [infra/README.md](infra/README.md).

## Phát triển

Cần `uv` (Python 3.12+) và `bun`.

    make setup                        # cài thư viện backend và frontend
    cd frontend && bun run dev:mock   # dashboard với backend giả, không cần dịch vụ nào
    cd frontend && bun run build      # mức kiểm bắt buộc của frontend
    cd backend/apps/agent && uv run agent serve --profile agents/rag --home ~/.contete-agent

Không có `make` (Windows thuần) thì chạy tay các lệnh trong từng công thức của `Makefile`.

## Thư mục

| Đường dẫn | Nội dung |
|---|---|
| `backend/packages/agent-core` | lõi: vòng lượt, tool, hook, hình của ca (`agentcore`) |
| `backend/apps/agent` | dịch vụ agent (`agent_app`), profile `agents/rag`, các plugin trong `plugins/` |
| `backend/apps/agent/plugins` | `web` (đăng nhập, dashboard), `knowledge` (kho tri thức, tìm kiếm), `jev` (chấm bằng chứng), `skills`, `conversations`, `follow_up`, `connectors` |
| `connectors/zalo` | connector Zalo, dịch vụ riêng nói chuyện với agent qua giao thức có ký ([docs/CONNECTOR-PROTOCOL.md](docs/CONNECTOR-PROTOCOL.md)) |
| `frontend` | dashboard (TanStack Start, bun) và backend giả để phát triển |
| `infra` | compose, Caddy, sao lưu và khôi phục |
| `docs` | kế hoạch và thiết kế |

## Luật làm việc

[AGENT.md](AGENT.md), [luật harness H1–H11](.claude/rules/agent-harness.md), [luật ranh giới L1–L7](.claude/rules/agent-boundary.md).
Test chỉ có e2e qua UI (`frontend/e2e`); mức kiểm là `bun run build` chạy được và backend khởi động được.

## Nguồn gốc

Tách từ dự án phòng khám Pema ngày 2026-11-18 (tag `split-base`); phần nối CRM bỏ hẳn ngày 2026-11-19. Nhiều tài liệu
trong `docs/` viết trước ngày đó và còn nhắc tới CRM: đọc như lịch sử. Giấy phép của mã nguồn gốc:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
