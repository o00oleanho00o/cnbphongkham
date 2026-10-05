# ported from: prototype/shared/guide.js (articles roles, crm01, records; rewritten for this app)
# ruff: noqa: E501  (the article texts are prose; a line break would change the Markdown)
"""Three synthetic articles for the staff guide (package U, step U7): text sources of ``agent.kb_document``
tagged ``guide``. Everything is invented for the demo (AGENT.md): no patient data, no real clinic protocol.

The rows are inserted with status ``cho_xu_ly`` so the ingest worker cuts them into chunks like any source
typed in ``/admin/kb``; the guide itself reads the text of the row, so it works before that. The ids are fixed
(``guide-...``) and the insert is ``ON CONFLICT DO NOTHING``: running it twice, or after a clinic edited an
article, changes nothing.

Run alone::

    PEMA_DATABASE_URL=postgresql+psycopg://be_app:...@localhost:5432/pema uv run python -m pema.clinic.actions.seed_guide
"""

from __future__ import annotations

import asyncio
import sys
from typing import Final
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.core.event_loop import ensure_selector_event_loop_policy

ARTICLES: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "guide-bat-dau-theo-vai-tro",
        "Bắt đầu theo vai trò",
        "Tất cả",
        """Biết nơi bắt đầu và người nhận bàn giao tiếp theo. Mỗi bộ phận làm việc trên cùng hành trình của người bệnh, \
với mục tiêu và điểm kiểm tra riêng.

## Cách thực hiện

1. **Lễ tân:** tìm đúng hồ sơ ở **Tìm bệnh nhân**, xếp lịch phù hợp, xác nhận hoặc check-in khi người bệnh đến.
2. **Bác sĩ:** mở Patient 360, xem lịch sử, cảnh báo và phản hồi, rồi ghi nhận và duyệt hướng dẫn.
3. **Chăm sóc khách hàng:** mở **Hôm nay** để xử lý việc đến hạn, ghi kết quả liên hệ, chuyển bác sĩ khi cần.
4. **Quản lý và chủ phòng khám:** xem **Hàng đợi duyệt**, **Vòng đời khách hàng** và các màn quản trị agent.

## Thông tin đi tiếp như thế nào?

Mỗi lần bàn giao cần rõ ba điều: ai phụ trách, việc nào đã xong và bước tiếp theo là gì. Có lịch hẹn không có \
nghĩa đã điều trị; đã thu tiền không có nghĩa đã hoàn tất chăm sóc.

## Điểm cần nhớ

- Người bệnh chỉ nhận được phản hồi đã được người có quyền duyệt. Nháp của trợ lý nằm ở **Hàng đợi duyệt**.
- Nội dung này là dữ liệu mẫu; không nhập hồ sơ người bệnh thật khi thử.
""",
    ),
    (
        "guide-cskh-viec-hom-nay",
        "CSKH chủ động: xử lý việc hôm nay",
        "CSKH",
        """Đúng người, đúng việc, đúng mốc chăm sóc. Hệ thống tạo việc từ quy tắc chăm sóc; nhân viên là người liên \
hệ và ghi lại kết quả.

## Cách thực hiện

1. Mở **Hôm nay**. Lọc theo trạng thái, kênh, nhóm chăm sóc hoặc bật **Của tôi**.
2. Mở một việc, đọc lý do, liệu trình còn lại và ngày dự kiến quay lại trước khi liên hệ.
3. Chọn kênh (gọi điện, Zalo, SMS hoặc ghi chú nội bộ), chọn kết quả và ghi nội dung đã trao đổi.
4. Không nghe máy, gọi lại hoặc đang bận: bắt buộc chọn ngày giờ liên hệ tiếp theo; việc chuyển sang trạng thái hẹn lại.
5. Đồng ý đặt lịch: điền lịch ngay trong cùng bước lưu. Chưa lưu được lịch thì việc chưa hoàn tất.
6. Có phản hồi sau điều trị hoặc khiếu nại: chọn kết quả tương ứng để chuyển sang bác sĩ xem.

## Thông tin đi tiếp như thế nào?

Kết quả liên hệ là ghi nhận nội bộ. Hệ thống không tự gửi lời khuyên y khoa. Tin nhắn gửi cho khách phải qua \
**Hàng đợi duyệt** hoặc là mẫu tin đã được bác sĩ duyệt.

## Điểm cần nhớ

- Khách đã từ chối quảng bá thì không nhận tin kết nối lại hoặc quảng bá; sinh nhật không bao giờ tự động gửi.
- Xem nhóm khách theo vòng đời ở **Vòng đời khách hàng**.
""",
    ),
    (
        "guide-ho-so-patient-360",
        "Hồ sơ và Patient 360",
        "Bác sĩ",
        """Đọc bối cảnh trước khi ghi thêm một sự kiện. Danh sách giúp tìm đúng người; Patient 360 cho biết người \
đó đang ở đâu trong quá trình chăm sóc.

## Cách thực hiện

1. Vào **Tìm bệnh nhân**, tìm bằng tên hoặc mã hồ sơ. Ô tìm kiếm ở thanh trên cũng mở cùng danh sách.
2. Mở hồ sơ để kiểm tra thông tin nhận diện, lần khám gần nhất, ngày dự kiến quay lại và số buổi còn lại.
3. Đọc các việc chăm sóc đang mở, lịch hẹn, liệu trình và dòng thời gian trước khi quyết định bước tiếp theo.
4. Xem hội thoại và các đồng ý của khách; ảnh chỉ được dùng khi khách đã đồng ý.

## Thông tin đi tiếp như thế nào?

Lịch sử cho biết điều gì đã được ghi nhận và bởi ai. Tiến độ số buổi chỉ là số buổi đã hoàn tất, không phải \
tỷ lệ cải thiện của da.

## Điểm cần nhớ

- Bác sĩ chỉ mở hồ sơ mình phụ trách hoặc có lịch hẹn của mình.
- Trợ lý chỉ soạn nháp; bác sĩ xem, sửa và duyệt, không có chẩn đoán tự động.
""",
    ),
)


async def seed_guide_articles(db: ClinicDatabase) -> int:
    """Insert the articles a clinic lacks; returns how many were inserted."""
    clinic_id: UUID = await get_installation_clinic_id(db)
    inserted = 0
    async with db.session() as session:
        for article_id, title, topic, body in ARTICLES:
            result = await session.execute(
                text(
                    "INSERT INTO agent.kb_document (clinic_id, id, name, kind, format, raw_text, byte_size, tags) "
                    "VALUES (:c, :id, :name, 'text', 'md', :body, :size, CAST(:tags AS text[])) "
                    "ON CONFLICT (clinic_id, id) DO NOTHING"
                ),
                {
                    "c": clinic_id,
                    "id": article_id,
                    "name": title,
                    "body": body,
                    "size": len(body.encode("utf-8")),
                    "tags": ["guide", topic],
                },
            )
            inserted += int(result.rowcount or 0)  # type: ignore[attr-defined]
    return inserted


async def _run() -> int:
    from pema.config.env import get_settings

    db = ClinicDatabase(get_settings().database_url)
    try:
        inserted = await seed_guide_articles(db)
    finally:
        await db.dispose()
    sys.stdout.write(f"Guide articles added: {inserted}.\n")
    return 0


def main() -> int:
    ensure_selector_event_loop_policy()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
