# ported from: src/video/kiem-gioi-han-video.ts
"""Check whether a video is inside the allowed limits.

RUNS AFTER the info-reading step, BEFORE the send step. That is the whole point of the design: both sources
return ``duration`` at the metadata step (costing exactly one request), so a 2-hour video is refused without
the server downloading a single byte.

Split from the tool because this is a pure rule: it touches no network, no disk, no Zalo, so it can be tested
directly instead of building a whole agent turn.

No forced deviation (``toFixed(1)`` is ``f"{x:.1f}"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pema.video.thong_tin_video import ThongTinVideo


@dataclass(frozen=True)
class GioiHanVideo:
    thoi_luong_toi_da: float
    """Minutes."""
    dung_luong_toi_da: float
    """MB."""


@dataclass(frozen=True)
class KetQuaKiemOk:
    ok: Literal[True] = True


@dataclass(frozen=True)
class KetQuaKiemLoi:
    loi: str
    ok: Literal[False] = False


KetQuaKiem = KetQuaKiemOk | KetQuaKiemLoi


def _so_gon(x: float) -> str:
    """JS ``String(number)``-like: ``30`` not ``30.0`` (the limit is echoed to the user)."""
    return str(int(x)) if float(x).is_integer() else str(x)


def phut_dep(ms: float) -> str:
    phut = ms / 60_000
    # Under 1 minute say it in seconds: "0,3 phút" is very hard to picture.
    if phut < 1:
        return f"{round(ms / 1000)} giây"
    dep = f"{phut:.1f}".removesuffix(".0")
    return f"{dep} phút"


def kiem_gioi_han_video(video: ThongTinVideo, gh: GioiHanVideo) -> KetQuaKiem:
    # ``duration_ms = 0`` means the source did NOT SAY, not a 0-second video. Blocking here is blocking
    # unjustly; letting it pass still leaves the size ceiling. Chosen to let it pass because refusing a
    # valid video for missing data is the worse outcome.
    if video.duration_ms > 0:
        tran_ms = gh.thoi_luong_toi_da * 60_000
        if video.duration_ms > tran_ms:
            return KetQuaKiemLoi(
                loi=(
                    f"Video dài {phut_dep(video.duration_ms)}, vượt mức cho phép "
                    f"{_so_gon(gh.thoi_luong_toi_da)} phút. "
                    "Nói với người dùng con số này và rằng mức đó chỉnh được ở trang Cấu hình."
                )
            )

    if video.file_size is not None and video.file_size > 0:
        tran_byte = gh.dung_luong_toi_da * 1024 * 1024
        if video.file_size > tran_byte:
            mb = f"{video.file_size / 1024 / 1024:.1f}"
            return KetQuaKiemLoi(
                loi=(
                    f"Video nặng {mb} MB, vượt mức cho phép {_so_gon(gh.dung_luong_toi_da)} MB. "
                    "Nói với người dùng con số này."
                )
            )

    return KetQuaKiemOk()
