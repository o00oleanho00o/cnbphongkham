# ported from: src/agent/tools/tai-video-tool-description.ts
"""Description of the ``tai_video`` tool.

It only says what the model can NOT work out from the schema, in the style of
``schedule_task_tool_description``. It gives no concrete example the model could copy verbatim: a lesson
paid for in ``create_image_tool_description`` (a "5 point design brief" made every image come out of one
mould).

Three things MUST be in the description:

1. ONLY TikTok, Facebook and Instagram. Left unsaid, the model calls the tool with a YouTube/Threads link
   and gets an error, wasting a turn.
2. It sends DIRECTLY and does not return a link. The model often thinks the tool returns a link to paste
   into the answer, and the user then receives a URL instead of the video.
3. A RE-POSTED video keeps its watermark, which cannot be removed. This is a real limit of the problem (the
   watermark already sits inside the original file) and the user needs to hear the reason rather than
   think the bot did something wrong.

The Vietnamese text below is read by the model and is kept verbatim.
"""

from __future__ import annotations

TAI_VIDEO_DESCRIPTION = (
    "Tải video từ link TikTok, Facebook hoặc Instagram rồi GỬI THẲNG vào cuộc trò chuyện này. "
    "Chỉ nhận ba nguồn đó - link YouTube, Threads hay nơi khác đều không dùng được.\n"
    "Tool tự gửi video, KHÔNG trả đường dẫn cho bạn chép lại. Gọi xong chỉ cần nói ngắn "
    "gọn là đã gửi, đừng dán lại link.\n"
    "Video quá dài sẽ bị từ chối kèm số phút cụ thể - đọc con số đó cho người dùng nghe.\n"
    "Bản tải về đã bỏ watermark của TikTok. Nhưng nếu video là bản ĐĂNG LẠI (người đăng "
    "tải từ nơi khác rồi đăng lên), watermark đã nằm sẵn trong file gốc và không gỡ được - "
    "gặp trường hợp đó thì nói thật với người dùng, đừng hứa gửi bản sạch hơn."
)
