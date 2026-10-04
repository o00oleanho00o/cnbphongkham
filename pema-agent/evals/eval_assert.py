# ported from: evals/eval-assert.ts
"""Score one case: compare what was observed with what was expected.

Kept apart from the runner and PURE on purpose: this is where it is easiest to be wrong and it cannot be
checked by the eval itself (a real model gives a different result each run). Apart, ``pytest`` scores it with
hand-built data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from evals.eval_case_type import EvalCase
from evals.eval_formatting_view import DinhDangDaGui


@dataclass(frozen=True)
class ToolDaGoi:
    """Name + JSON arguments of one tool call, for ``kiem_tra_tool_args``."""

    name: str
    input: str


@dataclass(frozen=True)
class QuanSat:
    tool_da_goi: list[str] = field(default_factory=list[str])
    """Names of the tools called, in order, with repeats."""
    tra_loi: str = "một câu trả lời bình thường"
    """The text the user really receives."""
    loi_chay: str | None = None
    """If the turn raised, the message; None when it ran through."""
    tool_da_goi_kem_args: list[ToolDaGoi] | None = None
    dinh_dang: DinhDangDaGui | None = None
    """Formatting that really reached Zalo, for ``kiem_tra_dinh_dang``.

    Optional so every hand-built ``QuanSat`` of older tests needs no change; a case that asserts formatting
    without this field is scored FAILED rather than skipped: silently skipping is exactly the false green this
    file exists to stop."""


def phat_hien_luot_hong(*, tokens: int, tra_loi: str, cau_loi_he_thong: list[str]) -> str | None:
    """Did this turn REALLY reach the model.

    REQUIRED, and the lesson of the first real run: the evals went through ``processBatch`` (the production
    path), which CATCHES the error and sends a "technical problem" sentence instead of raising. So when the
    router refused (404, missing credential) ``loi_chay`` was None, no tool was called, and 3 of 5 cases
    passed:

    * ``khong-tra-thua`` expects "no tool called" -> the turn died so that was true
    * ``cong-cu-hep``    expects "reply longer than 10 characters" -> the error sentence is longer
    * ``dinh-dang``      expects "no markdown" -> the error sentence has none

    Green exactly when the system is broken is the most dangerous false green: it says the opposite of the
    truth. Recognised by TWO independent signs, either one means broken:

    * ``total_tokens == 0``: the error branch of the turn processor closes the turn with usage {0,0,0}. A turn
      that really ran never has 0 tokens.
    * The reply EQUALS one of the system error sentences. The constants production passes in are used, not a
      hand-made word probe.
    """
    clean = tra_loi.strip()
    if any(clean == c.strip() for c in cau_loi_he_thong):
        return "Bot trả câu báo lỗi hệ thống - lượt agent đã hỏng, không phải hành vi của model"
    if tokens == 0:
        return "Lượt tiêu 0 token - chưa từng gọi được tới model"
    return None


@dataclass(frozen=True)
class KetQuaCham:
    dat: bool
    ly_do_hong: list[str]


def cham_case(c: EvalCase, qs: QuanSat) -> KetQuaCham:
    ly_do_hong: list[str] = []

    # A turn that raised is FAILED, not "no tool called so it passes". Without this branch a
    # ``khong_goi_tool`` case would be GREEN when the provider is dead: the most dangerous false green, green
    # exactly when the system is broken.
    if qs.loi_chay:
        ly_do_hong.append(f"Lượt agent ném lỗi: {qs.loi_chay}")
        return KetQuaCham(dat=False, ly_do_hong=ly_do_hong)

    da_goi = set(qs.tool_da_goi)
    md = c.mong_doi

    for t in md.goi_tool:
        if t not in da_goi:
            da_ra = ", ".join(qs.tool_da_goi) or "không tool nào"
            ly_do_hong.append(f'Phải gọi "{t}" nhưng không gọi (đã gọi: {da_ra})')

    for t in md.khong_goi_tool:
        if t in da_goi:
            ly_do_hong.append(f'Không được gọi "{t}" nhưng đã gọi')

    # Count on the LIST, not on the set: the whole point of this measure is the number of calls
    dem = Counter(qs.tool_da_goi)
    for t, so_lan_can in md.goi_tool_it_nhat.items():
        so_lan_thuc = dem[t]
        if so_lan_thuc < so_lan_can:
            ly_do_hong.append(f'Phải gọi "{t}" ít nhất {so_lan_can} lần, thực tế {so_lan_thuc} lần')

    kt = md.kiem_tra_text
    if kt is not None and not kt.dat(qs.tra_loi):
        ly_do_hong.append(f"Câu trả lời không đạt yêu cầu cấu trúc: {kt.mo_ta}")

    kdd = md.kiem_tra_dinh_dang
    if kdd is not None:
        if qs.dinh_dang is None:
            ly_do_hong.append(
                "Case khẳng định định dạng nhưng người chạy không cung cấp - xem QuanSat.dinh_dang"
            )
        elif not kdd.dat(qs.dinh_dang):
            ly_do_hong.append(f"Định dạng không đạt yêu cầu: {kdd.mo_ta}")

    kta = md.kiem_tra_tool_args
    if kta is not None:
        cac_loi_goi = [g for g in (qs.tool_da_goi_kem_args or []) if g.name == kta.tool]
        if not cac_loi_goi:
            ly_do_hong.append(f'Phải gọi "{kta.tool}" để kiểm tham số nhưng không gọi lần nào')
        elif not any(kta.dat(g.input) for g in cac_loi_goi):
            # Passes when AT LEAST ONE call is right: the model may call a tool several times in one turn, and
            # demanding every call to be right is a source of random red.
            ds = " | ".join(g.input for g in cac_loi_goi)
            ly_do_hong.append(f'Tham số "{kta.tool}" không đạt: {kta.mo_ta} (đã gọi với: {ds})')

    # No expectation at all is a meaningless case: it is ALWAYS green, so it only makes the result table look
    # fuller than it is
    if (
        not md.goi_tool
        and not md.khong_goi_tool
        and not md.goi_tool_it_nhat
        and md.kiem_tra_text is None
        and md.kiem_tra_dinh_dang is None
        and md.kiem_tra_tool_args is None
    ):
        ly_do_hong.append("Case không khai mong đợi nào - luôn xanh nên vô nghĩa")

    return KetQuaCham(dat=not ly_do_hong, ly_do_hong=ly_do_hong)
