# ported from: src/config/runtime-tuning-settings.ts (public API; first version by package A)
"""Effective value of the tuning parameters: an override (entered on the admin screen) wins over the
environment, which wins over the default of ``tuning_specs``.

THIS FILE IS THE CROSS-PACKAGE API: ``get_tuning`` is called from 55 files of the original (history store,
scheduler, channels, tools, knowledge, mcp, ...). Its signature is therefore FIXED by package A so every
package can code and test against it before D1 lands:

* ``get_tuning(key) -> TuningValue`` : synchronous, cheap, never raises for a known key;
* ``bot_time_zone() -> str``          : the most-read parameter (18 call sites in the original); one function
  so no call site reads the environment and forgets that the admin screen may have changed the zone;
* ``install_tuning_provider(provider)`` / ``reset_tuning_provider()`` : how D1's DB-backed provider (and
  tests) plug in.

Forced deviation (SQLite -> Postgres, sync -> async): the original read ``runtime_settings`` synchronously on
EVERY call ("reading again each time is the whole point of putting it on the web"). Python cannot await in a
plain call, so the override source is a ``TuningProvider`` that D1 backs with a short-lived in-memory
snapshot of ``agent.runtime_settings`` (refreshed on write and on a timer, a few seconds at most). A changed
value therefore still takes effect without a restart; it just is not instantaneous. The default provider
here has no overrides, so before D1 lands behaviour is "environment, then default".

Validation on READ is kept: a bad stored value is ignored (falls back) instead of killing the bot.
Booleans are the string ``"true"``; enums must be one of ``options``; a time zone must be valid (a broken
zone that slipped in by hand-editing the DB would make luxon fall back to UTC silently, shifting every
schedule by 7 hours); numbers must be finite and inside ``[min, max]``.
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pema.config.tuning_specs import TUNING_SPECS, TuningSpec, TuningValue
from pema.shared.current_datetime import is_valid_timezone
from pema.shared.ky_tu_moi_token import uoc_token_tu_ky_tu

if TYPE_CHECKING:
    from pema.config.runtime_settings_store import RuntimeSettingsSnapshot


class UnknownTuningKeyError(KeyError):
    """The key is not one of the 72 tuning parameters."""


class TuningProvider(Protocol):
    def override(self, key: str) -> str | None:
        """Raw stored override for ``key`` (the string as saved), or ``None`` when there is none."""
        ...


class _NoOverrides:
    def override(self, key: str) -> str | None:
        return None


class StaticTuningProvider:
    """Overrides from a dict. For tests and for D1's snapshot (which swaps the dict atomically)."""

    def __init__(self, overrides: Mapping[str, str | int | float | bool] | None = None) -> None:
        self._overrides: dict[str, str] = {}
        self.replace(overrides or {})

    def replace(self, overrides: Mapping[str, str | int | float | bool]) -> None:
        self._overrides = {k: _to_raw(v) for k, v in overrides.items()}

    def override(self, key: str) -> str | None:
        return self._overrides.get(key)


def _to_raw(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


_provider: TuningProvider = _NoOverrides()


def install_tuning_provider(provider: TuningProvider) -> None:
    global _provider
    _provider = provider


def reset_tuning_provider() -> None:
    install_tuning_provider(_NoOverrides())


def _parse(spec: TuningSpec, raw: str) -> TuningValue | None:
    """Parse ``raw`` for ``spec``; ``None`` when it is not valid (the caller then falls back)."""
    if spec.kind == "boolean":
        return raw == "true"
    if spec.kind == "enum":
        return raw if raw in spec.options else None
    if spec.kind == "timezone":
        return raw if is_valid_timezone(raw) else None
    try:
        number = float(raw)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    if (spec.minimum is not None and number < spec.minimum) or (
        spec.maximum is not None and number > spec.maximum
    ):
        return None
    if isinstance(spec.default, int) and number.is_integer():
        return int(number)
    return number


def _env_or_default(key: str, spec: TuningSpec) -> TuningValue:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return spec.default
    if spec.kind == "boolean":
        return raw.strip().lower() in {"true", "1", "yes", "on"}
    parsed = _parse(spec, raw)
    return spec.default if parsed is None else parsed


def tuning_default(key: str) -> TuningValue:
    """Value WHEN NO override exists: the environment if set, else the default (``macDinh``)."""
    spec = TUNING_SPECS.get(key)
    if spec is None:
        raise UnknownTuningKeyError(key)
    return _env_or_default(key, spec)


def get_tuning(key: str) -> TuningValue:
    """Effective value. A corrupt stored value is ignored rather than killing the bot."""
    spec = TUNING_SPECS.get(key)
    if spec is None:
        raise UnknownTuningKeyError(key)
    fallback = _env_or_default(key, spec)
    raw = _provider.override(key)
    if raw is None:
        return fallback
    parsed = _parse(spec, raw)
    return fallback if parsed is None else parsed


def get_tuning_int(key: str) -> int:
    """``get_tuning`` for a number parameter, as an int (most of them are counts or milliseconds)."""
    value = get_tuning(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} is not a number parameter")
    return int(value)


def get_tuning_bool(key: str) -> bool:
    value = get_tuning(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} is not a boolean parameter")
    return value


def bot_time_zone() -> str:
    """Effective time zone. One function because it is read from the most places (see module docstring)."""
    value = get_tuning("BOT_TIMEZONE")
    return value if isinstance(value, str) else str(TUNING_SPECS["BOT_TIMEZONE"].default)


# --------------------------------------------------------------------------------------------------------
# Package D1: the rest of runtime-tuning-settings.ts (list, cross rules, DB writes).
#
# The DB key of an override is ``tuning_<KEY>`` (``PREFIX`` of the original) in ``agent.runtime_settings``;
# the
# ``RuntimeSettingsSnapshot`` is the ``TuningProvider`` that makes ``get_tuning`` read it (its ``override``
# adds
# the prefix). Writes are async and go through the snapshot (write-through, see ``runtime_settings_store``).

TUNING_PREFIX = "tuning_"


@dataclass(frozen=True)
class TuningListItem:
    key: str
    value: TuningValue
    mac_dinh: TuningValue
    """The value WHEN NO override row exists: the environment if the deployer set it, else the default. The
    browser needs it to know when to send ``null`` (delete the override) instead of writing a value identical
    to the default; without it, toggling a switch off and on leaves an override row and the UI says "edited"
    for ever although the value equals the default."""
    from_env: bool
    """True = no override row: the value comes from the environment or the default."""


def list_tuning() -> list[TuningListItem]:
    """Every parameter with its effective value and whether it is overridden (``listTuning``)."""
    from pema.config.runtime_settings_store import current_settings_clinic, get_runtime_settings

    overridden = current_settings_clinic() is not None
    snapshot = get_runtime_settings()
    return [
        TuningListItem(
            key=key,
            value=get_tuning(key),
            mac_dinh=tuning_default(key),
            from_env=not (overridden and snapshot.read(TUNING_PREFIX + key) is not None),
        )
        for key in TUNING_SPECS
    ]


RAM_MOI_LUOT_YTDLP_MB = 75
"""RAM of one yt-dlp process, MEASURED: 72.8 MB peak and FIXED, not following the video size (~73 MB is Python
itself): downloading a 40 MB video only reached 75.6 MB because it writes straight to the stream instead of
gathering."""

PHAN_RAM_CHO_VIDEO = 0.25
"""The share of the server RAM allowed for video at the peak; the rest is for the bot process, the database
and the operating system."""


def kiem_ram_video(co_mb: float, song_song: float, ram_may_mb: float) -> str | None:
    """Does this video configuration fit the RAM of the server?

    Takes ``ram_may_mb`` as a PARAMETER and does not call the OS itself: a door inside a function that touches
    the system cannot be watched. The lesson paid for in ``envToiThieu``: tested hard as a function, but
    whether
    it is USED was measured by nobody.
    """
    dinh_mb = song_song * (co_mb + RAM_MOI_LUOT_YTDLP_MB)
    tran_mb = round(ram_may_mb * PHAN_RAM_CHO_VIDEO)
    if dinh_mb <= tran_mb:
        return None
    return (
        f"Dung lượng tối đa {co_mb:g} MB x {song_song:g} lượt cùng lúc cần tới {dinh_mb:g} MB bộ nhớ "
        f"lúc cao điểm, vượt mức an toàn {tran_mb} MB của máy chủ này "
        f"({ram_may_mb / 1024:.1f} GB RAM). Video được giữ trong bộ nhớ chứ không ghi ra "
        "đĩa, nên hạ một trong hai số."
    )


class _MemoryStatus(ctypes.Structure):
    _fields_ = (
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    )


def total_memory_mb() -> float:
    """RAM of this machine in MB (``os.totalmem()``): ``sysconf`` on Linux, ``GlobalMemoryStatusEx`` on
    Windows
    (the development machines). 0 when unknown, which makes the video rule refuse nothing it cannot measure
    only if the caller treats 0 as unknown: ``validate_tuning`` skips the rule then."""
    if sys.platform == "win32":
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
        return status.ullTotalPhys / 1024 / 1024 if ok else 0.0
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 / 1024
    except (ValueError, OSError, AttributeError):
        return 0.0


memory_probe: Callable[[], float] = total_memory_mb
"""The seam the video cross rule reads the RAM through (tests replace it)."""


@dataclass(frozen=True)
class _CrossRule:
    keys: tuple[str, ...]
    check: Callable[[Callable[[str], float]], str | None]


def _rule_turn_vs_image(so: Callable[[str], float]) -> str | None:
    if so("LLM_TURN_TIMEOUT_MS") <= so("IMAGE_GEN_TIMEOUT_MS"):
        return (
            "Trần thời gian mỗi lượt phải lớn hơn trần thời gian mỗi ảnh - "
            "nếu không, lượt bị cắt trước khi ảnh kịp xong."
        )
    return None


def _rule_stall_vs_image(so: Callable[[str], float]) -> str | None:
    if so("IMAGE_GEN_STALL_MS") >= so("IMAGE_GEN_TIMEOUT_MS"):
        return (
            "Thời gian im lặng phải nhỏ hơn trần thời gian mỗi ảnh, nếu không nó không bao giờ có tác dụng."
        )
    return None


def _rule_send_delay(so: Callable[[str], float]) -> str | None:
    if so("SEND_DELAY_MIN_MS") > so("SEND_DELAY_MAX_MS"):
        return "Giãn nhịp gửi tối thiểu không được lớn hơn tối đa."
    return None


def _rule_context_vs_output(so: Callable[[str], float]) -> str | None:
    # The bot only uses 70% of the context ceiling (room for what the model writes and for the tool results
    # that accumulate, see ``ngan_sach_an_toan``). A ceiling not clearly larger than what the model may write
    # lets the output eat that reserve before any context text.
    if so("LLM_CONTEXT_WINDOW") * 0.3 <= so("LLM_MAX_OUTPUT_TOKENS"):
        return (
            "Cửa sổ ngữ cảnh quá nhỏ so với trần token bot viết ra: bot chừa 30% cửa sổ cho phần viết ra và "
            "cho kết quả công cụ, nên cửa sổ phải lớn hơn khoảng 3,4 lần trần token viết ra."
        )
    return None


def _rule_document_vs_output(so: Callable[[str], float]) -> str | None:
    # The bot writes the file content INTO the tool call, so the document ceiling in characters must fit
    # inside
    # the token ceiling with room for thinking and the answer. The conversion MUST use ``KY_TU_MOI_TOKEN``:
    # the
    # SAME constant the context trimmer uses. This used to be a private 4 (the ENGLISH figure, 4.5 measured)
    # in a
    # Vietnamese bot while the real estimator runs at 2.5: the rule allowed 45,875 characters while the
    # estimator
    # only tolerates 28,672 (60% apart): someone setting 40,000 saved fine and the bot was cut off mid-file,
    # exactly what this rule exists to prevent.
    if uoc_token_tu_ky_tu(int(so("DOCUMENT_MAX_CHARS"))) > so("LLM_MAX_OUTPUT_TOKENS") * 0.7:
        return (
            "Trần ký tự tài liệu quá lớn so với trần token bot viết ra - "
            "bot sẽ bị cắt giữa lúc tạo file và mất cả lượt."
        )
    return None


def _rule_kb_result_budget(so: Callable[[str], float]) -> str | None:
    # I2: the result ceiling must HOLD what kb_search puts in, or the last chunks are silently dropped (the
    # root
    # bug: KB_TOP_K=5 and =20 once gave IDENTICAL results because the ceiling was too small for both).
    #
    # Review round 3: the round-2 formula (chunkChars + 140) missed the OVERLAP (``chen_chong_lan`` of
    # chunk-text: a chunk under the same heading is prefixed with up to ``chunkChars * overlapPercent/100``
    # characters of the previous one, default 10%, so real content ~1320 for chunk=1200): fixed by multiplying
    # ``chunkChars * (1 + overlapPercent/100)``. 150 per chunk = 13 (label frame) + 80 (source name, a HIGH
    # real
    # case, NOT the hard ceiling of 200 of ``kb-routes``: adding 210 instead of 150 made the shipped default
    # ``KB_MAX_RESULT_CHARS=8000`` break its own rule, 5*(1200*1.1+210)+520=8170>8000) + 50 (a 3-level
    # breadcrumb, the "balance point" of the heading-aware chunking research) + 7 (separator). 520 = the
    # envelope (wrapping tag + 3 lines of instruction), measured 313-513 (513 = the real hard ceiling, the
    # source name is cut at 200 characters in ``wrapUntrustedContent``).
    max_real = so("KB_CHUNK_CHARS") * (1 + so("KB_CHUNK_OVERLAP_PERCENT") / 100)
    if so("KB_MAX_RESULT_CHARS") < so("KB_TOP_K") * (max_real + 150) + 520:
        return (
            f"Trần ký tự kết quả ({so('KB_MAX_RESULT_CHARS'):g}) nhỏ hơn tổng chỗ mà "
            f"{so('KB_TOP_K'):g} đoạn x "
            f"{so('KB_CHUNK_CHARS'):g} ký tự (cộng chồng lấn {so('KB_CHUNK_OVERLAP_PERCENT'):g}%) "
            "cần - kết quả "
            "sẽ bị cắt và mấy đoạn cuối không bao giờ tới được bot. Hạ số đoạn, độ dài đoạn hay chồng lấn, "
            "hoặc nâng trần ký tự kết quả."
        )
    return None


def _rule_video_ram(so: Callable[[str], float]) -> str | None:
    # The bytes of a video now live in RAM, not on disk: ``uploadAttachment`` takes a Buffer and the user
    # decided against constant download-delete wearing the SSD. In exchange peak RAM = parallel runs x (video
    # size + ~73 MB for the yt-dlp process, FIXED because that is Python itself).
    #
    # Without this rule the two sliders allow 2000 MB x 8 runs = 16 GB, and no single input sees it: the kind
    # of
    # bug that only shows when SEVERAL parameters combine. Anchored on the REAL RAM of the machine and not on
    # an
    # invented number: the same configuration is fine on a 16 GB machine and dies on a 1 GB VPS.
    ram = memory_probe()
    if ram <= 0:
        return None
    return kiem_ram_video(so("VIDEO_MAX_SIZE_MB"), so("VIDEO_MAX_CONCURRENT"), ram)


LUAT_CHEO: tuple[_CrossRule, ...] = (
    _CrossRule(("LLM_TURN_TIMEOUT_MS", "IMAGE_GEN_TIMEOUT_MS"), _rule_turn_vs_image),
    _CrossRule(("IMAGE_GEN_STALL_MS", "IMAGE_GEN_TIMEOUT_MS"), _rule_stall_vs_image),
    _CrossRule(("SEND_DELAY_MIN_MS", "SEND_DELAY_MAX_MS"), _rule_send_delay),
    _CrossRule(("LLM_CONTEXT_WINDOW", "LLM_MAX_OUTPUT_TOKENS"), _rule_context_vs_output),
    _CrossRule(("DOCUMENT_MAX_CHARS", "LLM_MAX_OUTPUT_TOKENS"), _rule_document_vs_output),
    _CrossRule(
        ("KB_MAX_RESULT_CHARS", "KB_TOP_K", "KB_CHUNK_CHARS", "KB_CHUNK_OVERLAP_PERCENT"),
        _rule_kb_result_budget,
    ),
    _CrossRule(("VIDEO_MAX_SIZE_MB", "VIDEO_MAX_CONCURRENT"), _rule_video_ram),
)
"""The constraints BETWEEN parameters, the thing nobody sees by looking at two separate inputs (setting the
turn
ceiling below the image ceiling kills a valid image turn).

Each rule names the fields it concerns and applies ONLY when the user is changing one of them. Otherwise an
existing configuration that is already off (set by hand in ``.env``, or a rule added later) would block EVERY
save and lock the whole Settings page with no way left to fix it. Hit for real in the tests: the test
environment lowered the token ceiling to 2048 so no other field could be saved."""


def validate_tuning(sau: Mapping[str, TuningValue]) -> list[str]:
    """Validate the cross rules for the values the user is about to save.

    ``sau``: the values the user just changed; a field not here takes its current value, so editing one field
    of a pair is still checked against the other. Returns the messages (empty = valid).
    """

    def so(key: str) -> float:
        value = sau.get(key)
        if value is None:
            value = get_tuning(key)
        return float(value)

    dang_doi = set(sau)
    loi: list[str] = []
    for rule in LUAT_CHEO:
        if not any(key in dang_doi for key in rule.keys):
            continue
        message = rule.check(so)
        if message:
            loi.append(message)
    return loi


async def set_tuning(
    clinic_id: UUID,
    key: str,
    value: TuningValue | None,
    *,
    snapshot: RuntimeSettingsSnapshot | None = None,
) -> None:
    """Set a new value; ``None`` deletes the override, back to the environment (``setTuning``)."""
    from pema.config.runtime_settings_store import get_runtime_settings

    if key not in TUNING_SPECS:
        raise UnknownTuningKeyError(key)
    snap = snapshot or get_runtime_settings()
    if value is None:
        await snap.delete(clinic_id, TUNING_PREFIX + key)
        return
    await snap.set(clinic_id, TUNING_PREFIX + key, _to_raw(value))


async def reset_tuning(clinic_id: UUID, *, snapshot: RuntimeSettingsSnapshot | None = None) -> None:
    """Delete every tuning override of the clinic."""
    from pema.config.runtime_settings_store import get_runtime_settings

    snap = snapshot or get_runtime_settings()
    await snap.delete_many(clinic_id, [TUNING_PREFIX + key for key in TUNING_SPECS])
