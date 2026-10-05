# ported from: evals/preflight-web-search.ts
"""Check a PRECONDITION: is the web search service alive, BEFORE running the cases.

Why a separate step instead of letting the cases go red by themselves: when search returns 0 results the
research case still goes red, but with the reason "did not call web_fetch". The reader of the table then goes
to fix the persona, the model, the rules, while what is broken is somewhere else entirely. Nearly an hour was
lost on exactly this on 2026-08-06, and it nearly led to the wrong conclusion that the persona rule just
edited made the model worse.

Same habit as ``dung_eval_env`` when an API key is missing: a missing precondition STOPS everything, never a
half run that ends in a wrong table.

Pure module: the search function is injected, so it is testable without touching the network. Forced
deviation: async function instead of a Promise, ``KetQuaTienDe`` is a small dataclass instead of a union.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from evals.eval_case_type import EvalCase


def can_tra_cuu_web(c: EvalCase) -> bool:
    """Does this case depend on web lookup: only those need the precondition."""
    ten = [*c.mong_doi.goi_tool, *c.mong_doi.goi_tool_it_nhat.keys()]
    return any(t in {"web_search", "web_fetch"} for t in ten)


@dataclass(frozen=True)
class KetQuaTienDe:
    ok: bool
    loi: str = ""


async def kiem_tra_tien_de_tra_cuu(
    tim_kiem: Callable[[str], Awaitable[int]], nha_cung_cap: str
) -> KetQuaTienDe:
    """``tim_kiem`` returns the NUMBER of results. Runs 2 different queries before concluding: one empty
    query may just be a bad query, two ordinary queries both empty mean the service is dead."""
    truy_van = ["tin kinh tế hôm nay", "thời tiết Hà Nội"]
    so_ket_qua: list[int] = []

    for q in truy_van:
        try:
            so_ket_qua.append(await tim_kiem(q))
        except Exception:
            # A network error counts as empty: it must not bring the whole runner down
            so_ket_qua.append(0)

    if any(n > 0 for n in so_ket_qua):
        return KetQuaTienDe(ok=True)

    return KetQuaTienDe(
        ok=False,
        loi=(
            f"Dịch vụ tra cứu web ({nha_cung_cap}) trả về 0 kết quả cho cả {len(truy_van)} truy vấn thử.\n"
            '  DỪNG bộ eval: mọi case tra cứu sẽ đỏ với lý do "không gọi web_fetch", mà đó là\n'
            "  chẩn đoán SAI - model có tìm, chỉ là không nhận được URL nào để mở.\n"
            "  Kiểm tra cấu hình tra cứu ở trang Tools trên dashboard (DuckDuckGo hay bị chặn;\n"
            "  Brave cần API key), rồi chạy lại."
        ),
    )
