# ported from: evals/eval-cases-cach-noi.ts
"""Cases about HOW THE BOT TALKS: ask back when information is missing, do not interrogate when it is complete,
ask everything in one go, and no markdown leaking into a Zalo message."""

from __future__ import annotations

import re

from evals.eval_case_type import EvalCase, KiemTraDinhDang, KiemTraText, LichSuTin, MongDoi
from evals.eval_formatting_view import KIEU, DinhDangDaGui, dem_kieu, doan_theo_kieu

# Real-STYLE persona for the presentation cases.
#
# ``run_eval`` builds the agent with an EMPTY persona by default, while the real bot always has its own
# persona of a thousand characters. That gap once made the eval green while the user still saw the fault:
# breaking a persona rule did NOT reproduce the fault with an empty persona, but reproduced at once with a
# real one.
#
# Modelled on a real persona (form of address, tone, length), not copied: an eval must not depend on data in a
# user's DB.
PERSONA_KIEU_THAT = """Bạn là Minh Triết, trợ lý Zalo thông minh, thân thiện và vui tính.

Cách xưng hô:
- Tự xưng là "Minh Triết" hoặc "mình".
- Gọi người dùng là "bạn". Nếu người dùng xưng hô khác thì linh hoạt đáp lại cho phù hợp.

Phong cách giao tiếp:
- Trả lời tự nhiên như một người bạn thông minh đang trò chuyện trên Zalo.
- Vui vẻ, hài hước, có duyên nhưng không lố, không châm chọc.
- Có thể dùng emoji vừa phải cho cuộc trò chuyện sinh động hơn.
- Ưu tiên câu trả lời ngắn gọn, dễ hiểu, đi thẳng vào vấn đề.
- Khi nội dung phức tạp thì trình bày rõ ràng theo từng bước.

Cách làm việc:
- Luôn cố gắng hiểu mục tiêu thật sự của người dùng trước khi trả lời.
- Yêu cầu thiếu thông tin hoặc có nhiều cách hiểu thì hỏi lại thay vì tự suy đoán.
- Không bịa đặt thông tin. Không chắc thì nói rõ và đề nghị cung cấp thêm dữ liệu.
- Chủ động gợi ý phương án tốt hơn khi thấy yêu cầu chưa tối ưu.

Tính cách: thông minh, nhanh nhạy, nhiệt tình, hài hước và đáng tin cậy."""

# Has an emoji or not; written apart so a long escape run is not stuffed into the middle of an assertion
CO_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")

_DONG_KE_BANG = re.compile(r"^\s*\|[-:|\s]*--[-:|\s]*$", re.MULTILINE)
_TIEU_DE_MD = re.compile(r"^\s*#{1,6}\s", re.MULTILINE)
_DANH_SO = re.compile(r"^\s*\d+\.\s", re.MULTILINE)
_THE_MAU_SOT = re.compile(r"<(do|cam|vang|xanh|gach)>", re.IGNORECASE)
_THE_MAU_SOT_DONG = re.compile(r"</?(?:do|cam|vang|xanh|gach)>", re.IGNORECASE)
_KHOE_XEM_GIO = re.compile(r"xem (ngày )?giờ|ngày giờ (hiện tại|chính xác)", re.IGNORECASE)


def _hoi_gop_dat(t: str) -> bool:
    # Only an UPPER bound, no question mark required: same reason as hoi-lai-khi-thieu. Three question marks
    # or more is really piecemeal asking.
    return len(t.strip()) >= 20 and t.count("?") <= 2


def _dinh_dang_khong_trang_tri(dd: DinhDangDaGui) -> bool:
    return (
        dem_kieu(dd, KIEU.to) == 0
        and dem_kieu(dd, KIEU.cam) == 0
        and dem_kieu(dd, KIEU.do) == 0
        and dem_kieu(dd, KIEU.xanh) == 0
        and dem_kieu(dd, KIEU.vang) == 0
        and dem_kieu(dd, KIEU.dam) <= 1
    )


def _danh_sach_de_luot_mat_dinh_dang(dd: DinhDangDaGui) -> bool:
    dam = doan_theo_kieu(dd, KIEU.dam)
    # Styling a long sentence is the same as not styling: it must be a label or a short phrase
    return sum(1 for d in dam if len(d) <= 40) >= 4


def _thu_moi_dinh_dang(dd: DinhDangDaGui) -> bool:
    mau = dem_kieu(dd, KIEU.cam) + dem_kieu(dd, KIEU.do) + dem_kieu(dd, KIEU.xanh) + dem_kieu(dd, KIEU.vang)
    return mau >= 1 and dem_kieu(dd, KIEU.dam) >= 1


CASE_CACH_NOI: list[EvalCase] = [
    EvalCase(
        ten="hoi-lai-khi-thieu",
        ly_do=(
            "12-Factor #7 'Contact Humans with Tool Calls': agent CHỦ ĐỘNG hỏi khi thiếu thông tin. "
            "Tạo file rỗng rồi mới biết sai là tốn công cả hai bên - người dùng phải nói lại từ đầu, "
            "mà bot đã kịp gửi một file vô nghĩa vào cuộc trò chuyện."
        ),
        tin_nhan="tạo file Excel giúp mình với",
        # ``create_excel_file`` stays ON in this case: it must be measured that the model REFRAINS from
        # calling it, and turning it off would make it unable to call it even if it wanted to.
        #
        # The reply is NOT required to contain a question mark, although the first version did. The first
        # real run produced "Bạn gửi mình toàn bộ thông tin trong một lần để mình làm đúng ngay:" followed by
        # a bullet list: it gathered the right things and made no file, only written as an imperative so it
        # has no question mark. Demanding one asserts on PHRASING, exactly what this suite forbids; and
        # editing the persona so it always ends in a question mark would make the answer worse to please a
        # wrong measure. The real invariant is ``khong_goi_tool``: missing information means do NOT act.
        disabled_tools=["create_image", "create_word_document"],
        mong_doi=MongDoi(
            khong_goi_tool=["create_excel_file"],
            kiem_tra_text=KiemTraText(
                mo_ta="phải trả lời bằng chữ để xin thông tin, không im lặng",
                dat=lambda t: len(t.strip()) >= 30,
            ),
        ),
    ),
    EvalCase(
        ten="khong-hoi-van",
        ly_do=(
            "Mặt trái của case trên, và là hàng rào cho rủi ro lớn nhất của luật hỏi lại: luật quá "
            "rộng thì bot hỏi vặn cả câu hỏi kiến thức thường - tệ hơn hẳn so với cứ trả lời thẳng. "
            "Dòng thứ hai trong persona ('đừng hỏi vặn') sinh ra để chặn, case này canh nó."
        ),
        tin_nhan="thủ đô nước Pháp là gì vậy?",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            khong_goi_tool=["web_search", "web_fetch"],
            kiem_tra_text=KiemTraText(
                mo_ta="trả lời thẳng, KHÔNG kết thúc bằng câu hỏi ngược lại",
                # Only a question mark at the END counts: the bot may well repeat the user's question in the
                # middle of the answer, that is not interrogating
                dat=lambda t: not t.strip().endswith("?"),
            ),
        ),
    ),
    EvalCase(
        ten="hoi-gop-mot-lan",
        ly_do=(
            "Vai thứ ba của luật hỏi lại: gom hết thứ còn thiếu vào MỘT câu. Hỏi lắt nhắt qua nhiều "
            "lượt trên Zalo là cực kỳ khó chịu - mỗi lượt là một tin nhắn, người dùng phải trả lời "
            "ba lần cho một việc."
        ),
        tin_nhan="đặt lịch nhắc mình nhé",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            khong_goi_tool=["schedule_task"],
            kiem_tra_text=KiemTraText(
                mo_ta="xin thông tin trong MỘT tin, không rải quá 2 câu hỏi",
                dat=_hoi_gop_dat,
            ),
        ),
    ),
    EvalCase(
        ten="dinh-dang",
        ly_do=(
            "Yêu cầu 'lập bảng' là cái bẫy markdown tự nhiên nhất - model được huấn luyện để trả về bảng "
            "markdown, mà Zalo không có bảng. Đây là phép thử ĐẦU-CUỐI trên chữ THẬT SỰ tới sendMessage, "
            "khác với test đơn vị vốn tự dựng chuỗi đầu vào. GIỚI HẠN đã biết: từ khi lớp gửi DỊCH "
            "markdown thành Style thay vì xóa, ca này chỉ còn chứng minh 'không rò ký tự định dạng ra "
            "chữ' - nó KHÔNG chứng minh định dạng tới nơi, vì kiem_tra_text chỉ nhận text chứ không nhận "
            "styles. Phần đó do test đầu-cuối ở message-turn-sanitize.test.ts gánh."
        ),
        tin_nhan="lập bảng so sánh 3 loại cà phê: đen, sữa, bạc xỉu - giá và độ đậm",
        disabled_tools=["create_image", "create_word_document", "create_excel_file"],
        mong_doi=MongDoi(
            kiem_tra_text=KiemTraText(
                mo_ta="không còn ký tự định dạng markdown (**, ##, ```) và không còn dòng kẻ bảng",
                # Checks the table separator line TOO: ``ly_do`` calls this "the most natural markdown trap"
                # because the user asks for a table, but the first version only checked the other three
                # things so it never touched the table part of the cleaner: measuring something other than
                # what it claims to measure.
                dat=lambda t: (
                    "**" not in t
                    and _TIEU_DE_MD.search(t) is None
                    and "```" not in t
                    and _DONG_KE_BANG.search(t) is None
                ),
            )
        ),
    ),
    EvalCase(
        ten="dan-vao-thi-hoi-lai",
        ly_do=(
            "Hồi quy ĐÃ XẢY RA THẬT ngày 2026-08-05: thêm luật tô màu vào persona xong thì bot thôi hỏi "
            "lại. Cùng một nội dung dán vào, trước đó bot hỏi 'muốn xử lý theo hướng nào', sau đó tự "
            "trình bày lại luôn. Nguyên nhân là câu chữ mơ hồ - 'CHỈ khi người dùng nhờ soạn thư mời, "
            "thông báo' bị model đọc thành LOẠI NỘI DUNG chứ không phải LỜI YÊU CẦU. Đo A/B 3 lần mỗi "
            "nhánh: có khối màu 3/3 tự làm, bỏ khối màu 3/3 hỏi lại. Ca này ghim lại hành vi đúng."
        ),
        tin_nhan=(
            "THƯ MỜI THAM GIA KHÓA THIỀN THÁNG 8\n- Thời gian: 7h00 thứ Bảy ngày 08/08\n"
            "- Địa điểm: Chùa Từ Tân, Bảy Hiền, TPHCM\n- Đăng ký: https://forms.gle/abc123"
        ),
        disabled_tools=["create_image", "create_word_document", "create_excel_file", "web_search"],
        mong_doi=MongDoi(
            kiem_tra_text=KiemTraText(
                mo_ta="hỏi lại xem cần làm gì, KHÔNG tự trình bày lại kèm màu",
                # Both halves are needed: a question mark while still attaching the whole colour-tagged
                # original is still acting on its own, exactly what the user called "lởm".
                dat=lambda t: "?" in t and _THE_MAU_SOT.search(t) is None,
            )
        ),
    ),
    EvalCase(
        ten="danh-sach-de-luot-mat",
        # Real-style persona, NOT empty: the real bot always has its own persona, and an eval with an empty
        # persona cannot reproduce the production fault.
        persona=PERSONA_KIEU_THAT,
        ly_do=(
            "Sinh ra từ đúng lời phàn nàn của người dùng: hỏi 'bạn làm được gì' thì nhận về mười mấy gạch "
            "đầu dòng phẳng lì, không đậm không nhóm, đọc rất mệt. Căn nguyên là luật persona cũ viết theo "
            "LOẠI NỘI DUNG ('chỉ tô con số hoặc kết luận') - danh sách khả năng không có con số cũng không "
            "có kết luận nên theo đúng luật thì không gì được in đậm, model làm đúng y lời dặn. Luật mới "
            "nói theo NGUYÊN TẮC: tô cái người đọc lướt mắt tìm. Ca này chỉ đo được nhờ eval nhìn thấy "
            "styles - `kiem_tra_text` nhận chữ trần nên hoàn toàn mù với định dạng."
        ),
        tin_nhan="bạn làm được gì?",
        disabled_tools=["web_search", "web_fetch", "create_image"],
        mong_doi=MongDoi(
            kiem_tra_text=KiemTraText(
                mo_ta="có đánh số, có emoji dẫn mục, và KHÔNG khoe những việc người dùng tự làm được",
                # The user said it plainly: "I can check the time myself, why list it as a capability".
                # ``get_datetime`` is already marked ``counts_as_capability: false``.
                dat=lambda t: (
                    _DANH_SO.search(t) is not None
                    and CO_EMOJI.search(t) is not None
                    and _KHOE_XEM_GIO.search(t) is None
                ),
            ),
            kiem_tra_dinh_dang=KiemTraDinhDang(
                mo_ta="ít nhất 4 chỗ in đậm để lướt mắt bắt được ý, và chỗ tô là cụm ngắn chứ không phải cả câu",
                dat=_danh_sach_de_luot_mat_dinh_dang,
            ),
        ),
    ),
    EvalCase(
        ten="luat-thang-lich-su-cu",
        persona=PERSONA_KIEU_THAT,
        ly_do=(
            "Lỗ hổng NGHIÊM TRỌNG của chính bộ eval, lộ ra ngày 2026-08-05: eval chạy thread TRẮNG còn bot "
            "thật luôn có lịch sử. Sửa luật trình bày xong, eval xanh nhưng người dùng vẫn thấy kiểu cũ. "
            "Đo được: cùng system prompt, thread trắng 2/2 lần đánh số đúng luật mới, thread có câu trả lời "
            "cũ kiểu phẳng thì 2/2 lần chép lại kiểu cũ - model bắt chước chính nó mạnh hơn nghe luật. "
            "Chữa bằng một dòng persona nói thẳng 'luật thắng mọi ví dụ cũ trong lịch sử'; ca này ghim nó lại."
        ),
        tin_nhan="bạn làm được gì?",
        disabled_tools=["web_search", "web_fetch", "create_image"],
        # The old reply is written on purpose in the outdated style: flat, no numbers, no emoji
        lich_su_truoc=[
            LichSuTin(role="user", content="bạn làm được gì?"),
            LichSuTin(
                role="assistant",
                # Copies the exact SHAPE of the old reply in the wild (10 items, flat, no numbers, no emoji):
                # a shorter seed does NOT reproduce the pull to imitate.
                content=(
                    "Chào anh Hải, Minh Triết có thể hỗ trợ anh:\n"
                    "- Tra cứu web: tin công nghệ, AI, kinh tế, chính trị, giá vàng, tỷ giá, sự kiện mới...\n"
                    "- Tóm tắt và đối chiếu thông tin từ nhiều nguồn.\n"
                    "- Đọc ảnh: nhận diện chữ, số chứng từ, vé số, biển số, đếm và soi chi tiết.\n"
                    "- Đọc nội dung từ đường link công khai.\n"
                    "- Soạn và chỉnh nội dung: thư mời, thông báo, báo cáo, kế hoạch, bài giảng, bài đăng.\n"
                    "- Tạo và gửi file Word hoặc Excel có trình bày đẹp, bảng biểu và công thức.\n"
                    "- Thiết kế ảnh AI: poster, banner, cover, e-magazine; hoặc chỉnh sửa ảnh anh gửi.\n"
                    "- Đặt, xem, sửa và hủy lịch nhắc việc ngay trong cuộc trò chuyện này.\n"
                    "- Trong nhóm Zalo: xem danh sách thành viên, tag đúng người khi cần.\n"
                    "- Ghi nhớ những sở thích và thông tin anh chủ động chia sẻ để lần sau hỗ trợ nhanh hơn.\n\n"
                    "Nói ngắn gọn: anh đưa việc, Minh Triết giúp tra cứu, phân tích, soạn thảo hoặc đóng gói "
                    "thành file/ảnh cho gọn đẹp"
                ),
            ),
        ],
        mong_doi=MongDoi(
            kiem_tra_text=KiemTraText(
                mo_ta="vẫn đánh số theo luật mới, KHÔNG chép lại kiểu phẳng của câu trả lời cũ",
                dat=lambda t: _DANH_SO.search(t) is not None,
            )
        ),
    ),
    EvalCase(
        ten="tro-chuyen-thi-dung-trang-tri",
        persona=PERSONA_KIEU_THAT,
        ly_do=(
            "Chiều ngược của ca trên, và là lưới chặn mỗi lần nới luật định dạng: chuyện phiếm mà có tiêu "
            "đề to với màu mè thì đọc như tin quảng cáo. Thiếu ca này thì mọi lần nới luật đều có thể làm "
            "bot trang trí cả tin không cần, mà không ai bắt được."
        ),
        tin_nhan="chào bạn, hôm nay bạn thế nào?",
        disabled_tools=["web_search", "web_fetch", "create_image", "save_memory"],
        mong_doi=MongDoi(
            kiem_tra_dinh_dang=KiemTraDinhDang(
                mo_ta="không tiêu đề, không màu, nhiều nhất một chỗ in đậm",
                dat=_dinh_dang_khong_trang_tri,
            )
        ),
    ),
    EvalCase(
        ten="thu-moi-khi-duoc-nho",
        persona=PERSONA_KIEU_THAT,
        ly_do=(
            "Chiều KHẲNG ĐỊNH của luật màu: nhờ soạn thư mời thì phải thật sự có màu và emoji, không thì "
            "cả tính năng vô nghĩa. Đi cặp với `dan-vao-thi-hoi-lai` (chiều phủ định) - thiếu một trong "
            "hai thì sửa luật lệch hướng nào cũng còn nửa số ca vẫn xanh."
        ),
        tin_nhan=(
            "soạn giúp mình thư mời tham gia khóa thiền tháng 8 cho đẹp nhé: 7h00 thứ Bảy ngày 08/08 "
            "đến 09/08/2026, tại Chùa Từ Tân, 90/153 Trường Chinh, Bảy Hiền, TPHCM"
        ),
        disabled_tools=["create_image", "create_word_document", "create_excel_file", "web_search"],
        mong_doi=MongDoi(
            kiem_tra_text=KiemTraText(
                mo_ta="có emoji dẫn dòng và KHÔNG sót ký tự thẻ màu",
                dat=lambda t: _THE_MAU_SOT_DONG.search(t) is None and CO_EMOJI.search(t) is not None,
            ),
            kiem_tra_dinh_dang=KiemTraDinhDang(
                mo_ta="có ít nhất một đoạn được tô màu và có in đậm",
                dat=_thu_moi_dinh_dang,
            ),
        ),
    ),
]
