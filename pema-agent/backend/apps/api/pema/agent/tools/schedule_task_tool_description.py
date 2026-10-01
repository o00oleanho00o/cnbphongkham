# ported from: src/agent/tools/schedule-task-tool-description.ts
"""Description of the ``schedule_task`` tool - distilled from ``cronjob_tools.py`` of Hermes (section 7,
``thiet-ke-scheduler.md``), KEEPING ONLY the 4 points that have a FUNCTIONAL reason. No concrete example to
copy verbatim - the lesson paid for in ``create-image-tool-description.ts`` (stuffing a "5-item design brief"
made every image come out of one mould). The cron syntax example is the acceptable EXCEPTION: it is not a
matter of taste but the mandatory shape of the parameter (5 fields separated by spaces) that the model cannot
infer without it.
"""

from __future__ import annotations

SCHEDULE_TASK_DESCRIPTION = (
    "Đặt, xem, sửa hoặc hủy lịch để bot tự nhắn vào ĐÚNG cuộc trò chuyện này ở một mốc giờ "
    "trong tương lai (nhắc hẹn, báo cáo định kỳ...). Không đặt được lịch gửi sang hội thoại khác.\n"
    "action='create': kind='message' gửi nguyên văn payload lúc tới giờ, không tốn lượt LLM - "
    "dùng cho nhắc hẹn đơn thuần, RẺ HƠN NHIỀU. kind='agent' chạy một lượt agent (có tool) với "
    "payload là PROMPT - chỉ dùng khi lúc chạy cần tra cứu/tổng hợp gì đó.\n"
    "Payload của kind='agent' phải TỰ CHỨA đủ ngữ cảnh: lúc job chạy KHÔNG còn thấy lại cuộc "
    "trò chuyện hiện tại, chỉ có đúng payload này.\n"
    "action='list': xem lịch đang có trong cuộc trò chuyện này, trả về id từng lịch.\n"
    "MUỐN KIỂM TRA xem một lịch đã đặt được chưa thì dùng action='list'. TUYỆT ĐỐI không gọi lại "
    "action='create' để kiểm - làm vậy là đặt thêm một lịch trùng và người dùng nhận tin hai lần. "
    "Bạn KHÔNG thấy lại lời gọi tool của các lượt trước trong lịch sử hội thoại: đã nói với người "
    "dùng là đặt xong thì tin vào đó, đừng đặt lại cho chắc.\n"
    "action='cancel'/'update': PHẢI gọi action='list' trước để lấy đúng id - TUYỆT ĐỐI không tự đoán id.\n"
    "Sau khi tạo/sửa xong, đọc lại mốc giờ tool vừa trả cho người dùng nghe để họ xác nhận đúng ý."
)
