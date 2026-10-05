# ported from: src/zalo/reconnect-planner.ts
"""Kế hoạch kết nối lại cho listener zca-js. Tách THUẦN (không đụng đồng hồ/mạng thật) để test tất định.

VÌ SAO CÓ - ca thật (2026-08-25): người dùng ĐỔI MẬT KHẨU Zalo -> Zalo thu hồi MỌI phiên -> cookie web của bot
chết -> listener nối websocket được ("đã kết nối") nhưng bị Zalo từ chối phiên ngay (~2ms) -> đóng ->
reconnect
bằng đúng cookie chết -> LẶP VÔ TẬN mỗi ~1.8s. Bản cũ ``onConnected`` reset backoff ngay cả khi vừa nối
2ms, nên
bão không bao giờ lùi -> spam log + RỦI RO Zalo gắn cờ nick (ràng buộc #1 của dự án), mà người vận hành
không có
tín hiệu nào để biết là "phiên hết hạn, cần re-login".

Hai sửa chốt:
1. CHỈ reset backoff khi kết nối ĐỨNG đủ lâu (``on_dinh_ms``). Nối chớp-tắt tính là thất bại -> backoff
LÙI DẦN
   tới trần. Mạng chớp trên một kết nối lành thì vẫn reconnect nhanh; còn bão chớp-tắt (phiên chết) thì
   giãn ra.
2. Đếm số lần chớp-tắt LIÊN TIẾP; quá ngưỡng thì bật cờ nghi phiên chết để caller log cảnh báo "cần đăng nhập
   lại".

Where it runs: the listener itself lives in the Node bridge
(``backend/bridges/zalo-personal/src/zalo-listener.ts``)
which carries a TypeScript copy of this planner (same constants, same tests). This Python module is the
PORT-MAP
target and the reference implementation the API side uses to interpret ``account_state`` events.
"""

from __future__ import annotations

from dataclasses import dataclass

# Nối ngắn hơn mốc này coi là chớp-tắt (phiên chết/bị đá); dài hơn là lành
ON_DINH_MS = 5_000
BACKOFF_CO_SO_MS = 1_000
BACKOFF_TRAN_MS = 60_000
# Bao nhiêu lần chớp-tắt LIÊN TIẾP thì nghi phiên hết hạn (khuyên re-login)
NGUONG_NGHI_NGO = 5


@dataclass(frozen=True)
class KetQuaDong:
    delay_ms: int
    """Chờ bao lâu rồi hãy kết nối lại (đã cộng jitter)."""
    on_dinh: bool
    """Kết nối vừa rồi có ĐỨNG đủ lâu không (lành)."""
    chop_tat_lien_tiep: int
    """Số lần nối-rồi-rớt-ngay LIÊN TIẾP tính tới hiện tại."""
    nghi_ngo_phien_chet: bool
    """Đã đủ ngưỡng để nghi phiên hết hạn -> caller nên khuyên re-login."""


class KeHoachKetNoiLai:
    def __init__(
        self,
        *,
        on_dinh_ms: int = ON_DINH_MS,
        co_so_ms: int = BACKOFF_CO_SO_MS,
        tran_ms: int = BACKOFF_TRAN_MS,
        nguong_nghi_ngo: int = NGUONG_NGHI_NGO,
    ) -> None:
        self._so_lan = 0
        self._chop_tat_lien_tiep = 0
        self._ket_noi_luc: float | None = None
        self._on_dinh_ms = on_dinh_ms
        self._co_so_ms = co_so_ms
        self._tran_ms = tran_ms
        self._nguong_nghi_ngo = nguong_nghi_ngo

    def danh_dau_ket_noi(self, now: float) -> None:
        """Gọi khi listener báo đã kết nối. ``now`` (ms) do caller cấp."""
        self._ket_noi_luc = now

    def danh_dau_dong(self, now: float, jitter: int) -> KetQuaDong:
        """Gọi khi listener đóng. ``jitter`` (>= 0) do caller cấp để test tất định. Trả kế hoạch chờ + cờ nghi
        phiên chết."""
        on_dinh = self._ket_noi_luc is not None and now - self._ket_noi_luc >= self._on_dinh_ms
        if on_dinh:
            # Kết nối lành vừa rớt (mạng chớp) -> khởi động lại nhanh, quên chuỗi chớp-tắt.
            self._so_lan = 0
            self._chop_tat_lien_tiep = 0
        else:
            self._chop_tat_lien_tiep += 1
        # Tiêu một lần kết nối: lần đóng kế tiếp mà không có kết nối mới xen giữa thì KHÔNG được tính nhầm là
        # "đứng" theo mốc cũ.
        self._ket_noi_luc = None

        backoff = min(self._tran_ms, self._co_so_ms * 2**self._so_lan)
        delay_ms = backoff + jitter
        self._so_lan += 1

        return KetQuaDong(
            delay_ms=delay_ms,
            on_dinh=on_dinh,
            chop_tat_lien_tiep=self._chop_tat_lien_tiep,
            nghi_ngo_phien_chet=self._chop_tat_lien_tiep >= self._nguong_nghi_ngo,
        )
