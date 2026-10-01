# ported from: src/agent/persona-tool-rules.ts
"""Tool-usage rules of the system prompt, joined ONLY when the matching tool is switched on.

No forced deviation (pure module).

Before, every rule lived hard-coded in ``BASE_PERSONA``: switching "Vẽ ảnh AI" off on the dashboard removed
exactly that tool from the "Khả năng" section, but four lines teaching how to write an image prompt still
went along with every turn - measured at 1163 characters teaching the rules of a switched-off tool. That
costs tokens AND contradicts itself: the prompt says "do not promise anything outside the list" and then
teaches the bot how to do exactly that.

The way is taken from ``hermes-agent/agent/system_prompt.py`` ("Tool-aware behavioral guidance: only inject
when the tools are loaded"): the rule text lives in its own prompt module and is gated by tool name at
assembly time. NOT attached to the tool registry, because the registry also serves the dashboard API -
pushing prompt text to the browser would be waste.

Rename a tool in the registry and forget to fix it here, and the test ``test_persona_tool_rules`` goes red
at once instead of the rule silently disappearing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaRule:
    tools: list[str]
    """The rule shows when AT LEAST ONE tool of the list is on. An empty list = a general rule about using
    tools, shown whenever the account has ANY tool (exactly how Hermes gates ``PARALLEL_TOOL_CALL_GUIDANCE``
    by ``valid_tool_names``)."""
    text: str


# Rules tied to a specific tool - placed in the same group as the "Quy tắc trả lời" of the base persona
RULES_TRA_LOI: list[PersonaRule] = [
    PersonaRule(
        tools=["add_reaction", "send_file", "tag_member"],
        text=(
            "- Tool hành động (thả reaction, gửi file, tag thành viên) chỉ dùng khi thực sự phục vụ yêu "
            "cầu - không lạm dụng."
        ),
    ),
    PersonaRule(
        tools=["create_word_document", "create_excel_file"],
        text=(
            "- Xuất file (create_word_document / create_excel_file) chỉ khi người dùng yêu cầu file, "
            "hoặc nội dung là bảng số liệu dài đọc trong chat sẽ rối. Bảng số liệu ưu tiên Excel, văn "
            "bản/báo cáo thì Word. Hai tool này TỰ GỬI file rồi - đừng gọi send_file để gửi lại."
        ),
    ),
    PersonaRule(
        tools=["create_image"],
        text=(
            "- Vẽ ảnh (create_image) chỉ khi người dùng thật sự muốn có ẢNH: nhờ vẽ/tạo/thiết kế/làm "
            "poster, banner, e-magazine. Mất 1-3 phút mỗi ảnh nên đừng vẽ khi họ chỉ hỏi thông tin. Tool "
            "này TỰ GỬI ảnh rồi."
        ),
    ),
    PersonaRule(
        tools=["create_image"],
        text=(
            "- Prompt vẽ ảnh TRUNG THÀNH với ý người dùng: họ nói gì về phong cách, màu, bố cục thì đưa "
            "hết vào; họ không nói thì ĐỪNG TỰ BỊA ràng buộc. Bên nhận prompt là model biết thiết kế, để "
            "nó tự do thì mỗi lần ra một phương án khác nhau."
        ),
    ),
    PersonaRule(
        tools=["create_image"],
        text=(
            "- Người dùng gửi kèm ĐOẠN CHỮ để đưa vào ảnh (bài viết, tiêu đề, câu trích, bảng giá): CHÉP "
            'NGUYÊN VĂN vào prompt, đặt trong ngoặc kép, ghi rõ vai trò từng phần. Tóm tắt thành "chủ '
            'đề X" là hỏng - model vẽ ra chữ bịa thay vì chữ họ đưa. Giữ nguyên dấu tiếng Việt.'
        ),
    ),
    PersonaRule(
        tools=["create_image"],
        text=(
            '- Tham số mode của create_image: "ve_moi" cho hầu hết yêu cầu (poster, banner, '
            'e-magazine, minh họa - dù mô tả dài và chi tiết tới đâu). Chỉ dùng "sua_anh_da_gui" khi '
            "người dùng ĐÃ GỬI ẢNH trong hội thoại và nhờ sửa chính tấm đó."
        ),
    ),
    PersonaRule(
        tools=["schedule_task"],
        text=(
            "- Đặt/sửa lịch hẹn (schedule_task) xong: đọc lại mốc giờ tool vừa trả bằng lời cho người "
            'dùng nghe để họ xác nhận đúng ý (vd "15:00 ngày 01/08") - đọc lại là cách rẻ nhất để bắt '
            "lỗi hiểu sai giờ. Muốn hủy hoặc sửa lịch: LUÔN action='list' trước để lấy đúng id, TUYỆT "
            "ĐỐI không tự đoán id."
        ),
    ),
]

# The "narrate progress" block - meaningless when the account has no tool left: it teaches how to narrate
# BETWEEN tool calls, and without tools there is no step in between.
KHOI_KE_TIEN_TRINH = (
    "Quy tắc kể tiến trình (để chủ bot xem lại cách bạn làm việc):\n"
    '- TRƯỚC mỗi lần gọi tool, viết một câu ngắn nói bạn sắp làm gì và vì sao (vd "Cần giá vàng '
    'hôm nay - tra web trước.").\n'
    "- Bước sau khi tool trả về: mở đầu bằng một câu nhận xét dữ liệu đủ chưa, thiếu gì, bước kế "
    'là gì (vd "Đủ 2 nguồn khớp nhau - giờ đối chiếu và trả lời.").\n'
    "- Mấy câu tiến trình này nằm ở các bước GIỮA nên người dùng không thấy; riêng câu TRẢ LỜI "
    "CHỐT gửi cho người dùng thì TUYỆT ĐỐI không kèm chúng. Câu hỏi không cần tool thì trả lời "
    "thẳng, không kể tiến trình."
)

# Lookup block - every line is gated on its own because some lines are only true when a web tool exists
RULES_TRA_CUU: list[PersonaRule] = [
    PersonaRule(
        tools=["web_search"],
        text=(
            "- Thông tin thay đổi theo thời gian hoặc mới hơn dữ liệu huấn luyện (giá cả, tỷ giá, tỷ số, "
            "tin tức, lịch chiếu, thông tin sản phẩm, kết quả vừa công bố...) -> BẮT BUỘC dùng "
            'web_search trước. Không trả lời từ trí nhớ, không nói "mình không xem được" khi chưa thử '
            "tool."
        ),
    ),
    PersonaRule(
        tools=["web_search", "web_fetch"],
        text=(
            "- web_search cho danh sách trang; cần dữ liệu chi tiết thì web_fetch trang cụ thể. Trang "
            "đầu không có thứ cần tìm -> thử 1-2 trang khác trong kết quả hoặc đổi từ khóa, rồi mới được "
            "kết luận là không tìm thấy."
        ),
    ),
    # Measured on real Zalo 06/08/2026: a request to summarise market news produced 2 web_search calls and
    # 0 web_fetch calls - the model wrote 10 items from search snippets, so all of it was generic, with no
    # figures and no sources. The rule just above already says "need detail -> web_fetch", but the model
    # did not consider "summarise the news" as "needs detail", so the rule has to name that exact kind of
    # task.
    PersonaRule(
        tools=["web_search", "web_fetch"],
        text=(
            "- Tóm tắt tin tức hay báo số liệu thị trường: kết quả web_search chỉ là tiêu đề và đoạn "
            "trích, CHƯA ĐỦ để viết. Phải web_fetch 2-3 bài từ các nguồn KHÁC NHAU, và gọi chúng CÙNG "
            "MỘT LÚC trong một lượt chứ đừng đọc lần lượt. Mỗi ý nêu ra phải neo được vào bài đã đọc "
            "bằng con số, mốc thời gian hoặc tên tổ chức, và ghi nguồn NGAY DƯỚI mục đó (tên báo + ngày "
            "+ đường dẫn) chứ không gom một dòng chung ở cuối. Ý nào không neo được thì BỎ - năm tin có "
            "nguồn hơn hẳn mười tin nói chung chung."
        ),
    ),
    PersonaRule(
        tools=["kb_search"],
        text=(
            "- Câu hỏi về chính sách, bảng giá, quy trình, hướng dẫn của chỗ mình thì TRA kho tri thức "
            "trước, đừng trả lời bằng trí nhớ chung."
        ),
    ),
    PersonaRule(
        tools=["kb_search"],
        text=("- Trả lời DỰA TRÊN đoạn tra được, và nói rõ lấy từ tài liệu nào."),
    ),
    PersonaRule(
        tools=["kb_search"],
        text=(
            "- Tra không ra thì nói thật là chưa có trong tài liệu, TUYỆT ĐỐI không bịa số liệu, giá, "
            "hay thời hạn."
        ),
    ),
    PersonaRule(
        tools=[],
        text=(
            "- Cần nhiều thứ KHÔNG phụ thuộc nhau thì gọi tool cùng lúc trong một lượt (vd đọc 2-3 trang "
            "khác nhau), đừng gọi lần lượt từng cái. Mỗi lượt gọi tool phải gửi lại toàn bộ hội thoại "
            "nên gọi rời rạc tốn gấp nhiều lần. Chỉ làm tuần tự khi bước sau cần kết quả của bước trước."
        ),
    ),
    PersonaRule(
        tools=[],
        text=(
            "- Chỉ hỏi ngược lại người dùng khi thông tin KHÔNG THỂ lấy được bằng tool (vd cần ảnh chụp "
            "rõ hơn, thông tin cá nhân của họ)."
        ),
    ),
    PersonaRule(
        tools=[],
        text=(
            "- Lịch sử chat có thể chứa lượt trước bạn tra không ra - đó là chuyện cũ, có thể do lỗi đã "
            "được sửa. Lượt mới LUÔN thử tool lại từ đầu; không lặp lại câu trả lời thất bại cũ trong "
            "lịch sử."
        ),
    ),
    PersonaRule(
        tools=[],
        text=(
            "- Tool lỗi hay không ra kết quả: nói thật đã tìm ở đâu, TUYỆT ĐỐI không bịa số liệu. Việc "
            "dính đến tiền (báo giá, tỷ giá, số liệu tài chính) phải nêu nguồn và ngày của dữ liệu; tra "
            "cứu theo kỳ hay theo đợt phải đối chiếu đúng kỳ và đúng ngày người dùng hỏi, không lấy kỳ "
            "gần nhất rồi coi là xong."
        ),
    ),
]

TOOL_KEYS_IN_RULES: list[str] = list(
    dict.fromkeys(key for rule in [*RULES_TRA_LOI, *RULES_TRA_CUU] for key in rule.tools)
)
"""Every tool key that appears in a rule - the test checks them against the registry to catch a rename."""


def hop_le(rule: PersonaRule, available: set[str]) -> bool:
    if len(rule.tools) == 0:
        return len(available) > 0
    return any(tool in available for tool in rule.tools)


def tool_persona_sections(available_tool_keys: Sequence[str]) -> list[str]:
    """The rule blocks that follow the tools, filtered by the tool set the account REALLY gets.

    Returns a list of sections so ``build_system_prompt`` joins them exactly where it wants.
    """
    available = set(available_tool_keys)
    sections: list[str] = []

    tra_loi = [rule.text for rule in RULES_TRA_LOI if hop_le(rule, available)]
    if len(tra_loi) > 0:
        sections.append("Quy tắc dùng công cụ:\n" + "\n".join(tra_loi))

    if len(available) > 0:
        sections.append(KHOI_KE_TIEN_TRINH)

    tra_cuu = [rule.text for rule in RULES_TRA_CUU if hop_le(rule, available)]
    if len(tra_cuu) > 0:
        sections.append(
            "Quy tắc tra cứu thông tin (làm đúng thứ tự, đừng bỏ cuộc sớm):\n" + "\n".join(tra_cuu)
        )

    return sections
