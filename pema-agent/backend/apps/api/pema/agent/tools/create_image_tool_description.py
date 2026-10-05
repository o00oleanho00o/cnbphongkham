# ported from: src/agent/tools/create-image-tool-description.ts
"""Description of the image tool: split out because it is the easiest thing to write wrongly.

EXPENSIVE LESSON: a "5 point design brief" with concrete examples (text on the left, illustration on the
right, navy-to-violet background, cyan accent) was once put in here. The result was that EVERY image came
out of one mould, and uglier than before.

The reason: ``cx/gpt-5.5-image`` is NOT an image model. The router strips the ``-image`` suffix and calls
GPT-5.5 (a full chat model) directly with ``instructions: ""`` and an ``image_generation`` tool (see
``imageProviders/codex.js``, function buildBody). It reads the prompt as a user message and DESIGNS BY
ITSELF.

Measured: sending a bare prompt (exactly the sentence the user typed, no hints) 3 times gave 3 completely
different designs, all dense and professional, and it invented an icon cluster with Vietnamese text that
nobody asked for. Our brief only tied its hands.

Principle since then: this description only says what has a FUNCTIONAL reason (text must be verbatim, the
ratio must be said in the prompt because there is no parameter for it). ABSOLUTELY no aesthetic
prescription: no colour examples, no layout examples, no density. The taste of whoever writes the code
leaks in here and every image of every user gets it.

The Vietnamese text below is read by the model and is kept verbatim.
"""

from __future__ import annotations

CHU_PHAI_NGUYEN_VAN = (
    "CHỮ NGƯỜI DÙNG ĐƯA phải chép NGUYÊN VĂN vào prompt (tiêu đề, bài viết, câu trích, giá, tên, số điện thoại): "  # noqa: E501
    'đặt trong ngoặc kép, ghi rõ vai trò từng phần (TIÊU ĐỀ: "...", ĐOẠN MỞ: "...", TRÍCH DẪN: "..."). '
    'TUYỆT ĐỐI không tóm tắt thành chủ đề - viết "chủ đề thiền Phật giáo" thì ảnh ra chữ bịa, còn chép nguyên '  # noqa: E501
    "văn thì ra đúng chữ họ cần. Giữ nguyên dấu tiếng Việt, dặn viết đúng chính tả."
)
"""Functional reason: if not copied verbatim, the model draws invented text."""

TI_LE_NOI_TRONG_PROMPT = (
    "KÍCH THƯỚC/TỈ LỆ không có tham số riêng - muốn dọc, ngang, vuông hay tỉ lệ cụ thể (4:1, 16:9...) thì phải "  # noqa: E501
    "nói trong prompt."
)
"""Functional reason: the API has no size parameter, the model ignores ``size``."""

TRUNG_THANH_VOI_Y_NGUOI_DUNG = (
    "Prompt phải TRUNG THÀNH với ý người dùng. Họ nói gì về phong cách (sang trọng, tối giản, rực rỡ, cổ điển, "  # noqa: E501
    "trẻ trung...), màu sắc, bố cục, thứ muốn có trong ảnh thì đưa hết vào. Họ KHÔNG nói thì ĐỪNG TỰ BỊA ràng "  # noqa: E501
    "buộc - đừng tự chọn màu, đừng tự sắp bố cục, đừng tự quyết dày hay thoáng. Bên nhận prompt là một model "
    "biết thiết kế, để nó tự do thì mỗi lần ra một phương án khác nhau; áp sẵn phong cách là ảnh nào cũng như "  # noqa: E501
    "ảnh nào. Mô tả ngắn gọn đúng thứ người dùng cần còn hơn tả dài theo gu của bạn."
)
"""The most important: pass on exactly what the user means, do NOT add constraints. The receiver is a chat
model that knows design: left free it gives a different option each time; a preset style makes every image
alike."""

KHI_BI_CHE_XAU = (
    "Người dùng chê xấu hoặc nhờ chỉnh lại: viết prompt MỚI theo ĐÚNG hướng họ nêu (sang trọng hơn, tối giản hơn, "  # noqa: E501
    "nhiều màu hơn...), giữ nguyên phần chữ. Đừng gửi lại prompt cũ, cũng đừng tự đổi sang hướng họ không nhắc tới."  # noqa: E501
)
"""User says it is ugly: guess the direction they want, do not repeat the old prompt."""

CREATE_IMAGE_DESCRIPTION = (
    "Vẽ ảnh mới bằng AI hoặc SỬA ảnh người dùng vừa gửi, rồi gửi thẳng vào cuộc trò chuyện. "
    "Dùng khi người dùng nhờ vẽ/tạo/thiết kế ảnh (poster, banner, cover, e-magazine, minh họa), "
    "hoặc nhờ sửa ảnh họ gửi (đổi màu, xóa vật thể, đổi phong cách).\n"
    "Mất 1-3 phút mỗi ảnh nên chỉ gọi khi người dùng thật sự muốn có ảnh.\n"
    f"{CHU_PHAI_NGUYEN_VAN}\n"
    f"{TI_LE_NOI_TRONG_PROMPT}\n"
    f"{TRUNG_THANH_VOI_Y_NGUOI_DUNG}\n"
    f"{KHI_BI_CHE_XAU}"
)
