# ported from: src/zalo/sanitize-reply-text.ts
"""Lớp làm sạch CUỐI CÙNG trước khi chữ của model xuống Zalo - mảnh còn thiếu trong mô hình phân lớp của
OpenAI (lọc đầu vào, chống injection, rủi ro tool đều đã có; guardrail ĐẦU RA thì chưa).

Trước module này, `result.text` đi thẳng vào `sendReplyInParts`. Persona có DẶN "không markdown", nhưng dặn
không phải bảo đảm - và Zalo không render markdown nên `**đậm**` với `## Tiêu đề` hiện ra nguyên ký tự trước
mắt người dùng mỗi ngày.

Cố ý KHÔNG làm bộ kiểm duyệt nội dung. Đây là bot cá nhân; chỉ chữa ba thứ ĐO ĐƯỢC, không đoán ý.

CỐ Ý BỎ QUA `__đậm__` và `_nghiêng_`: dấu gạch dưới sống đầy trong tên file và URL thật (`bao_gia_2026.pdf`),
nên bắt chúng là đổi hỏng dữ liệu thật để chữa một dạng markdown model gần như không dùng khi đã được dặn viết
lời thường. Cũng bỏ qua `> trích dẫn` và danh sách đánh số - hai thứ đó đọc vẫn tự nhiên trên Zalo.

HAI LUẬT SỐNG CÒN của mọi biểu thức trong file này:

  1. KHÔNG ĐƯỢC NUỐT CHỮ. Hàm này chạm vào MỌI câu trả lời của bot, nên một biểu thức ăn tham làm mất nội
     dung còn tệ hơn nhiều so với việc để lọt vài ký tự định dạng. Vòng rà soát đầu đã bắt được hai ca nuốt
     trắng.
  2. PHẢI TUYẾN TÍNH. Bot đọc tin của người lạ, mà một tin soạn khéo khiến model nhại lại chuỗi độc là đủ để
     biểu thức bậc hai treo cả tiến trình - process này một luồng phục vụ mọi account, vòng tick scheduler
     lẫn HTTP dashboard. Nên MỖI biểu thức chỉ có MỘT lượng từ mở trên cùng một lớp ký tự; phần kiểm thêm
     làm bằng code, không bằng backtrack.

Module THUẦN: không env, không logger, không DB. `da_sua` trả ra ngoài để caller ghi log - sửa chữ của model
rồi im lặng là tự bịt mắt mình lúc chẩn đoán.

Forced deviations:

* ``DAU_HIEU_RO_PROMPT`` (``src/agent/prompt-leak-markers.ts``) and ``la_dong_sentinel``
  (``src/scheduler/silent-sentinel.ts``) live next to this module (``prompt_leak_markers``,
  ``silent_sentinel``): the guard and the producer of the markers are ONE constant, and the
  sentinel line is judged by ONE function.
* JS regex semantics are reproduced explicitly: ``\\w`` is ``[A-Za-z0-9_]``, ``\\s`` is the ECMAScript
  whitespace set, multiline ``^`` / ``$`` also break at CR, LS and PS, the ``i`` flag folds ASCII only (see
  ``utf16_text``).
* The caps of the link pattern (``{0,200}``, ``{0,500}``) count code points, not UTF-16 units: the text is not
  measured or cut here, so no offset depends on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .prompt_leak_markers import DAU_HIEU_RO_PROMPT
from .sanitize_code_block import MOC_KHOI, tach_khoi_code, tra_khoi_code_ve
from .silent_sentinel import la_dong_sentinel
from .utf16_text import JS_LINE_END, JS_LINE_START, JS_S, js_trim


@dataclass(frozen=True)
class KetQuaLamSach:
    # Chữ đã làm sạch. Rỗng khi `chan` - đừng gửi.
    text: str
    # Những thứ đã chỉnh, để log. Rỗng nghĩa là không đụng một ký tự nào.
    da_sua: list[str] = field(default_factory=list[str])
    # Chặn hẳn: câu trả lời rò system prompt, gửi nửa vời còn tệ hơn không gửi.
    chan: bool = False


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _bo_inline_code(text: str, da_sua: list[str]) -> str:
    sau = _INLINE_CODE_RE.sub(r"\1", text)
    if sau != text:
        da_sua.append("inline code")
    return sau


# `# Tiêu đề` -> `Tiêu đề`. Chỉ ở ĐẦU DÒNG, để `#hashtag` giữa câu không bị đụng.
_TIEU_DE_RE = re.compile(f"{JS_LINE_START}[ \\t]{{0,3}}#{{1,6}}[ \\t]+")


def _bo_tieu_de(text: str, da_sua: list[str]) -> str:
    sau = _TIEU_DE_RE.sub("", text)
    if sau != text:
        da_sua.append("tiêu đề")
    return sau


# `[chữ](url)` -> `chữ (url)`. Giữ URL vì đó là thông tin THẬT người dùng cần - bỏ luôn là làm mất nội dung,
# không phải làm sạch.
#
# MỘT lượng từ cho phần trong ngoặc, tách bằng code. Bản đầu dùng `([^)\s]+)[^)]*` - vừa bậc hai (hai lượng từ
# chồng miền), vừa VỨT TRẮNG phần đuôi vì `[^)]*` không nằm trong nhóm nào.
#
# ĐÒI phần trong ngoặc TRÔNG NHƯ một địa chỉ. Cú pháp `[...](...)` xuất hiện đầy trong văn bản thường mà
# không hề là liên kết, và đổi nó đi là làm hỏng chữ thật:
#
#   `Mã lô [A12](hàng nhập) đã về kho`  -> phải giữ NGUYÊN
#   `Gọi handlers[0](event) là được`    -> phải giữ NGUYÊN
#
# Cái giá: liên kết dùng đường dẫn tương đối (`[tài liệu](docs/a.md)`) không được đổi. Chấp nhận - để nguyên
# thì vẫn đọc được, còn đổi nhầm chữ thật thì không cứu lại được.
#
# `![alt](url)` (ảnh) cũng vào đây, dấu `!` bị nuốt cùng.
DIA_CHI_RE = re.compile(r"(https?://|www\.|mailto:|tel:|ftp://|/)", re.IGNORECASE | re.ASCII)

# KẸP TRẦN cho hai lượng từ là bắt buộc, không phải cho gọn.
#
# `\[([^\]\n]*)\]` không giới hạn thì mỗi dấu `[` mở đầu một lượt quét tới cuối dòng rồi thất bại - O(n^2)
# trên chuỗi toàn dấu mở. Đo thật: 51.200 dấu `[` mất 1,26 giây, 102.400 mất 5,8 giây (đủ treo cả tiến
# trình một luồng này). Kẹp trần biến nó thành O(n * trần).
#
# Con số chọn rộng rãi so với thực tế: chữ hiển thị của liên kết dài quá 200 ký tự thì không còn là nhãn, và
# URL dài quá 500 thì cắt bớt cũng chẳng ai bấm. Vượt trần thì chuỗi giữ NGUYÊN - không đổi còn hơn đổi sai.
LIEN_KET_RE = re.compile(r"!?\[([^\]\n]{0,200})\]\(([^)\n]{0,500})\)")


def _thay_lien_ket(match: re.Match[str]) -> str:
    nguyen_van, chu, trong = match.group(0), match.group(1), match.group(2)
    noi = js_trim(trong)
    if DIA_CHI_RE.match(noi) is None:
        return nguyen_van
    return f"{chu} ({noi})" if js_trim(chu) else noi


def _bo_lien_ket(text: str, da_sua: list[str]) -> str:
    sau = LIEN_KET_RE.sub(_thay_lien_ket, text)
    if sau != text:
        da_sua.append("liên kết")
    return sau


# `**đậm**` -> `đậm`. Chạy TRƯỚC phần nghiêng, nếu không thì bộ nghiêng ăn một dấu sao mỗi bên và để lại hai
# dấu lẻ.
#
# Vế `(?<![\w*])` ở dấu MỞ là bắt buộc, cùng lý do với phần nghiêng: thiếu nó thì `2**3**2 = 512` (luỹ thừa
# Python) ra `232`. Không thêm vế tương ứng ở dấu ĐÓNG để `**Giá**là 45k` vẫn dọn được.
_DAM_RE = re.compile(f"(?<![A-Za-z0-9_*])\\*\\*(?!{JS_S})([^*\\n]+?)(?<!{JS_S})\\*\\*")


def _bo_dam(text: str, da_sua: list[str]) -> str:
    sau = _DAM_RE.sub(r"\1", text)
    if sau != text:
        da_sua.append("in đậm")
    return sau


# `*nghiêng*` -> `nghiêng`.
#
# Hai thứ PHẢI giữ nguyên, và đó là lý do biểu thức khó đọc thế này:
#
#   - Gạch đầu dòng `-`: persona đang DẠY bot dùng nó để chia ý. Không đụng tới (biểu thức này chỉ nhìn dấu
#     sao nên vốn đã an toàn).
#   - Dấu sao giữa từ, kiểu `2*3*4`: phải ra đúng `2*3*4`. Chặn bằng cách đòi dấu mở KHÔNG đứng ngay sau ký
#     tự chữ/số - đúng luật "left-flanking" của CommonMark. Thiếu vế này thì `2*3*4` bị đọc thành `2` +
#     nghiêng(`3`) + `4` và một phép nhân biến thành `234`.
#
# Cũng đòi không có khoảng trắng ngay trong cặp: `a * b * c` là phép tính, không phải chữ nghiêng.
_NGHIENG_RE = re.compile(f"(?<![A-Za-z0-9_*])\\*(?!{JS_S})([^*\\n]+?)(?<!{JS_S})\\*(?![A-Za-z0-9_*])")


def _bo_nghieng(text: str, da_sua: list[str]) -> str:
    sau = _NGHIENG_RE.sub(r"\1", text)
    if sau != text:
        da_sua.append("in nghiêng")
    return sau


# Bỏ DÒNG PHÂN CÁCH của bảng markdown (`|---|---:|`).
#
# Chỉ bỏ đúng dòng đó, KHÔNG dựng lại cả bảng. Lý do: dòng phân cách là nhiễu thuần túy - không mang một chữ
# nào - nên bỏ đi là mất trắng; còn các dòng dữ liệu vẫn đọc được dạng "| A | B |", và tự dựng lại bảng
# thành văn xuôi thì phải đoán đâu là tiêu đề đâu là dữ liệu, đúng kiểu "làm quá" mà phase này tránh.
#
# MỘT lượng từ, điều kiện "có ít nhất hai gạch ngang liền nhau" kiểm bằng code. Bản đầu viết
# `[ \t:|-]*--[ \t:|-]*` - hai lượng từ trên lớp ký tự CÓ CHỨA `-` kẹp giữa là `--`, cho O(n^2): đo thật
# 25.600 dấu gạch mất 1,4 giây, và model hoàn toàn nhại lại được chuỗi đó nếu người lạ soạn tin bảo nó nhại.
_DONG_PHAN_CACH_RE = re.compile(f"{JS_LINE_START}[ \\t]*\\|[-:| \\t]*{JS_LINE_END}\\r?\\n?")


def _bo_dong_phan_cach_bang(text: str, da_sua: list[str]) -> str:
    sau = _DONG_PHAN_CACH_RE.sub(lambda m: "" if "--" in m.group(0) else m.group(0), text)
    if sau != text:
        da_sua.append("dòng kẻ bảng")
    return sau


# Bỏ THẺ MÀU/GẠCH CHÂN, giữ nguyên nội dung bên trong.
#
# Cần ở đây vì đường này là đường khi TẮT cấu hình định dạng: persona vẫn dạy model cú pháp
# `<cam>...</cam>`, nên thẻ vẫn có thể xuất hiện. Không bóc thì người dùng nhận nguyên chuỗi
# `<cam>Thời gian:</cam>` - tệ hơn hẳn so với mất màu. Cùng danh sách thẻ với `markdown_inline_styles.py`.
#
# Biểu thức TUYẾN TÍNH nhờ lớp ký tự phủ định `[^<\n]`, cùng luật với cả file.
THE_MAU_RE = re.compile(r"</?(?:do|cam|vang|xanh|gach)>", re.IGNORECASE | re.ASCII)


def _bo_the_mau(text: str, da_sua: list[str]) -> str:
    if "<" not in text:
        return text
    sau = THE_MAU_RE.sub("", text)
    if sau != text:
        da_sua.append("thẻ màu")
    return sau


_XUONG_DONG_RE = re.compile(r"\r?\n")


def _bo_sentinel(text: str, da_sua: list[str]) -> str:
    """Bỏ dòng CHỈ chứa nhãn `[SILENT]` lọt vào lượt chat THƯỜNG.

    Dùng `la_dong_sentinel` (cấp DÒNG), KHÔNG dùng `is_silent_response` (cấp CẢ CÂU TRẢ LỜI). Bản đầu dùng
    nhầm hàm cấp câu để lọc từng dòng, mà hàm đó có luật "mở đầu bằng [SILENT] thì nuốt cả câu" - nên
    "[SILENT] là nhãn nội bộ, dùng để bot im lặng ạ" (câu trả lời hợp lệ khi người dùng hỏi về chính cái
    nhãn) bị vứt sạch, người nhắn ngồi im không nhận gì.
    """
    if "[" not in text:
        return text
    dong = _XUONG_DONG_RE.split(text)

    # Lọc MỘT lần rồi suy ra "có đụng gì không" từ độ dài, thay vì gọi vị từ ở hai chỗ (`some` rồi
    # `filter`). Hai lời gọi là hai chỗ phải sửa cùng lúc, mà đổi lệch một cái thì hành vi phân kỳ âm thầm.
    giu = [d for d in dong if not la_dong_sentinel(d)]
    if len(giu) == len(dong):
        return text
    da_sua.append("nhãn [SILENT]")
    # Bỏ dòng RỖNG ở hai đầu (nhãn đi kèm một dòng trắng là chuyện thường), chứ KHÔNG `.trim()` cả chuỗi -
    # trim cả chuỗi thì ăn luôn khoảng trắng đầu dòng nội dung, mà mọi bước khác trong file này đều không
    # đụng tới khoảng trắng.
    while giu and js_trim(giu[0]) == "":
        giu.pop(0)
    while giu and js_trim(giu[-1]) == "":
        giu.pop()
    return "\n".join(giu)


def co_dau_hieu_ro_prompt(text: str) -> bool:
    """Câu trả lời có mẩu chữ đặc trưng của system prompt không."""
    return any(d in text for d in DAU_HIEU_RO_PROMPT)


def lam_sach_tra_loi(text: str) -> KetQuaLamSach:
    """Làm sạch câu trả lời của model trước khi gửi.

    Kiểm rò prompt trên chữ GỐC, trước khi bỏ định dạng: bỏ trước rồi kiểm thì một dấu hiệu có markdown xen
    vào (`**Quy tắc an toàn...`) đã bị đổi hình dạng, và bộ canh trượt đúng ca người ta cố tình lách.
    """
    if co_dau_hieu_ro_prompt(text):
        return KetQuaLamSach(text="", da_sua=["CHẶN: rò system prompt"], chan=True)

    da_sua: list[str] = []

    # Dọn ký tự NUL của model TRƯỚC khi dùng nó làm mốc. Docstring của MOC_KHOI nói "model không sinh ra nó" -
    # đó là giả định, không phải bất biến: JSON escape NUL là hợp lệ. Một chuỗi có dạng NUL + số + NUL sẽ va
    # đúng mốc và `tra_khoi_code_ve` nhét nội dung khối code vào nhầm chỗ.
    sach_nul = text.replace(MOC_KHOI, "") if MOC_KHOI in text else text

    # Khối code ra khỏi thân TRƯỚC mọi bước khác, trả về SAU cùng - nội dung bên trong khối là code, không
    # phải văn bản để dọn định dạng
    khoi_da_tach = tach_khoi_code(sach_nul, da_sua)

    ra = _bo_inline_code(khoi_da_tach.than, da_sua)
    ra = _bo_lien_ket(ra, da_sua)
    ra = _bo_tieu_de(ra, da_sua)
    ra = _bo_dam(ra, da_sua)
    ra = _bo_nghieng(ra, da_sua)
    ra = _bo_dong_phan_cach_bang(ra, da_sua)
    ra = _bo_the_mau(ra, da_sua)
    ra = _bo_sentinel(ra, da_sua)

    return KetQuaLamSach(text=tra_khoi_code_ve(ra, khoi_da_tach.khoi), da_sua=da_sua, chan=False)


def lam_sach_giu_dinh_dang(text: str) -> KetQuaLamSach:
    """Bản làm sạch cho đường GIỮ ĐỊNH DẠNG: chỉ giữ hai lá chắn thật sự là lá chắn, bỏ hết các bước XÓA
    markdown.

    Vì sao tách hàm chứ không thêm cờ vào `lam_sach_tra_loi`: hai đường có tập bước khác hẳn nhau, nhét cờ
    vào giữa một chuỗi 7 bước là mời gọi nhánh sai lặng lẽ. Đường cũ vẫn còn nguyên và là đường lui khi tắt
    cấu hình định dạng.

    Bước XÓA markdown chuyển hết sang `markdown_sang_style_zalo` - ở đó dấu markdown không bị vứt mà được
    DỊCH thành `TextStyle` của Zalo. Riêng khối code thì bộ dịch tự bảo vệ (giữ nguyên xi từng dòng), nên
    không cần `tach_khoi_code` ở đây nữa.
    """
    # Kiểm rò prompt trên chữ GỐC - cùng lý do đã ghi ở `lam_sach_tra_loi`
    if co_dau_hieu_ro_prompt(text):
        return KetQuaLamSach(text="", da_sua=["CHẶN: rò system prompt"], chan=True)

    da_sua: list[str] = []
    # NUL không phải markdown, là rác - không có lý do gì gửi nó lên Zalo
    sach_nul = text.replace(MOC_KHOI, "") if MOC_KHOI in text else text
    return KetQuaLamSach(text=_bo_sentinel(sach_nul, da_sua), da_sua=da_sua, chan=False)
