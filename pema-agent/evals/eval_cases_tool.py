# ported from: evals/eval-cases-tool.ts
"""Cases about USING TOOLS: does the model look things up instead of guessing, and the other way round, does it
skip the tool for what is already in the prompt."""

from __future__ import annotations

from evals.eval_case_type import EvalCase, KiemTraText, MongDoi

CASE_TOOL: list[EvalCase] = [
    EvalCase(
        ten="gio-chinh-xac",
        ly_do=(
            "System prompt CỐ Ý chỉ ghi ngày + thứ, KHÔNG ghi giờ (giờ đổi mỗi phút thì vỡ prompt cache "
            "mỗi phút - xem currentDateLine). Nên hỏi giờ là thứ model KHÔNG thể tự biết, buộc phải gọi "
            "get_datetime. Đoán giờ là sai chắc chắn, mà nói ra vẫn nghe rất tự tin.\n"
            "Bản đầu của case này hỏi 'hôm nay thứ mấy' và đòi gọi get_datetime - SAI: ngày đã nằm sẵn "
            "trong prompt, gọi tool là thừa, đúng thứ mà case khong-tra-thua phạt. Chính lần chạy thật "
            "bắt được mâu thuẫn đó."
        ),
        tin_nhan="bây giờ mấy giờ rồi bạn?",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(goi_tool=["get_datetime"]),
    ),
    EvalCase(
        ten="ngay-co-san",
        ly_do=(
            "Mặt trái của case trên, và là hàng rào cho một tối ưu dễ bị bỏ quên: dòng ngày trong system "
            "prompt tồn tại ĐỂ model khỏi phải gọi tool. Nếu model vẫn gọi get_datetime cho câu hỏi ngày "
            "thì dòng đó vô dụng mà vẫn tốn token mỗi lượt - lúc đó phải xem lại cách diễn đạt của nó."
        ),
        tin_nhan="hôm nay thứ mấy vậy bạn?",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            khong_goi_tool=["get_datetime", "web_search"],
            kiem_tra_text=KiemTraText(
                mo_ta="phải trả lời được bằng chữ, không im lặng",
                dat=lambda t: len(t.strip()) >= 5,
            ),
        ),
    ),
    EvalCase(
        ten="tin-tuc-phai-mo-bai",
        ly_do=(
            "Đo trên Zalo thật 06/08/2026 với Gemini: yêu cầu tóm tắt tin thị trường ra 2 lần "
            "web_search, 0 lần web_fetch. Model viết 10 mục từ đoạn trích tìm kiếm nên toàn ý chung "
            "chung, không con số, không mốc thời gian, không nguồn. Mô tả của web_search đã ghi sẵn "
            '"muốn đọc chi tiết thì gọi web_fetch" mà model vẫn không dùng - đây là nết cần luật '
            "persona ép, không phải thứ tự sửa được bằng đổi model (đo A/B: gemini-3.5-flash cũng "
            "đốt hết 8 bước mà vẫn chỉ tìm kiếm).\n"
            "Khẳng định trên HÀNH VI (có mở bài không) chứ không trên câu chữ, vì nội dung tin đổi "
            "mỗi ngày."
        ),
        tin_nhan="tóm tắt giúp tôi vài tin kinh tế thị trường nổi bật hôm nay",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            goi_tool=["web_search"],
            # AT LEAST TWO articles, not "reading is enough": measured on real Zalo, the old rule only asked
            # for one so the model opened exactly one and stopped, and all 10 items shared one source line at
            # the end. The run through the router opened 4 articles so each item had its own source: that is
            # what the user compares.
            goi_tool_it_nhat={"web_fetch": 2},
        ),
    ),
    EvalCase(
        ten="tra-cuu",
        ly_do=(
            "Câu hỏi về số liệu thay đổi hàng ngày. Model KHÔNG được trả lời bằng trí nhớ huấn luyện - "
            "giá vàng trong đầu model là giá của năm ngoái, mà nói ra vẫn nghe rất tự tin."
        ),
        tin_nhan="giá vàng SJC hôm nay bao nhiêu vậy?",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(goi_tool=["web_search"]),
    ),
    EvalCase(
        ten="khong-tra-thua",
        ly_do=(
            "Chiều ngược lại của hai case trên. Chỉ thưởng cho việc gọi tool thì model học cách gọi tool "
            "với MỌI tin nhắn - tốn token, chậm, và một lời chào thành ba lượt gọi mạng."
        ),
        tin_nhan="chào bạn nhé",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            khong_goi_tool=[
                "get_datetime",
                "web_search",
                "web_fetch",
                "read_image",
                "get_group_info",
                "save_memory",
                "schedule_task",
                "send_file",
            ]
        ),
    ),
    EvalCase(
        ten="cong-cu-hep",
        ly_do=(
            "Kiểm chứng lớp tắt tool theo agent (phase 02) ở tầng HÀNH VI, không chỉ tầng schema. "
            "Tool bị tắt thì model không những không gọi được, mà còn phải NÓI THẬT là không làm được - "
            "persona có dặn 'không hứa việc cần công cụ ngoài danh sách'. Hứa lèo rồi im là kết cục tệ nhất."
        ),
        tin_nhan="vẽ giúp mình con mèo đang ngủ nhé",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            khong_goi_tool=["create_image"],
            kiem_tra_text=KiemTraText(
                mo_ta="phải trả lời bằng chữ (nói thật là không vẽ được), không im lặng",
                dat=lambda t: len(t.strip()) >= 10,
            ),
        ),
    ),
    # The three regression barriers of the original ("ask back" lines of BASE_PERSONA) are not separate
    # scenarios here: in the original this comment closes the list and the three cases live in
    # ``eval_cases_cach_noi`` (hoi-lai-khi-thieu, khong-hoi-van, hoi-gop-mot-lan). They are NOT evidence for
    # the three persona lines: measured, removing the lines left all three green (gpt-combo asks back without
    # being told). They stay because they guard the behaviour of the WHOLE SYSTEM: a cheaper model, or someone
    # editing the persona to rush the model, turns them red before a user receives an empty Excel file.
]
