# ported from: src/agent/tool-loop-guard.ts
"""Block useless tool loops inside ONE agent turn.

Forced deviation (Vercel AI SDK -> own loop): the step shape the guard reads is ``model_types.RawStep``
(``tool_results`` + ``content`` parts of type ``tool-error``) instead of a structural TS type, and the
failure shape check is ``tool_failure_result.la_ket_qua_loi`` (D4).

Before this module the only upper bound was ``stepCountIs(8)``: a model calling ``web_fetch`` on the same
failing URL 5 times in a row burned 5/8 steps with nobody stopping it, the user waited and got a truncated
answer.

Three kinds of loop kept apart because the cure differs (the ``tool_guardrails.py`` model of Hermes):

* ``loi-giong-het``    same tool + same parameters + failed again. Retrying identically is hopeless, block
                       earliest.
* ``cung-tool-loi``    the same tool fails with DIFFERENT parameters. It may still be probing, so the
                       threshold is higher.
* ``khong-tien-trien`` a READ-ONLY tool returns the SAME result over and over. Not an error, but it adds
                       nothing either.

PURE module: no env, no DB, no log. The thresholds and the way to recognise a read tool are both injected,
so every branch can be tested without a model. The returned decision is DATA: the caller chooses whether to
turn it into a warning log or a stop condition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pema.agent.model_types import RawStep
from pema.agent.tool_call_signature import bam_ngan, chu_ky_lenh_goi, chuan_hoa_json
from pema.agent.tool_loop_guard_thresholds import NguongGuard, canh_bao_tu, nguong_theo_tran_step
from pema.agent.tools.tool_failure_result import la_ket_qua_loi

# Re-export: the signature and the thresholds are both part of this module's contract, the reader does not
# need to know which file they live in
__all__ = [
    "CHO_QUA",
    "MaQuyetDinh",
    "MucQuyetDinh",
    "NguongGuard",
    "QuyetDinh",
    "ToolLoopGuard",
    "canh_bao_tu",
    "chu_ky_lenh_goi",
    "nguong_theo_tran_step",
]

type MucQuyetDinh = Literal["cho-qua", "canh-bao", "chan"]
type MaQuyetDinh = Literal["", "loi-giong-het", "cung-tool-loi", "khong-tien-trien"]


@dataclass(frozen=True)
class QuyetDinh:
    muc: MucQuyetDinh
    ma: MaQuyetDinh
    """Short code to filter logs; empty when passing."""
    thong_diep: str
    tool: str
    so_lan: int


CHO_QUA = QuyetDinh(muc="cho-qua", ma="", thong_diep="", tool="", so_lan=0)


class ToolLoopGuard:
    """Reads BOTH sources of a step, and in this repo the second one is the MAIN source:

    * ``content`` of type ``tool-error``: only present when ``execute`` THREW. Here it almost never
      happens, every tool catches its error and returns a sentence to the model (a deliberate decision,
      see ``tools/tool_failure_result``). Still read, because SDK-level failures go this way: the schema
      rejects a bad input, the model invents a tool name.
    * ``tool_results`` whose ``output`` carries the failure mark: this is every real BUSINESS failure.

    The first version only counted ``tool-error`` so two of the three counters were dead code:
    ``web_fetch`` failing on 8 different URLs burned the whole step ceiling without the guard saying a word.
    """

    def __init__(self, nguong: NguongGuard, la_tool_doc: Callable[[str], bool]) -> None:
        """``la_tool_doc``: only READ tools get the "no progress" rule, writing twice with different
        results is legitimate."""
        self._nguong = nguong
        self._la_tool_doc = la_tool_doc
        self._dem_loi_giong_het: dict[str, int] = {}
        self._dem_cung_tool_loi: dict[str, int] = {}
        self._dem_khong_tien_trien: dict[str, tuple[str, int]] = {}
        """signature -> (hash of the latest result, how many times that result repeated)"""
        self._quyet_dinh_chan: QuyetDinh | None = None

    def da_chan(self) -> bool:
        """Whether the block is decided. STICKY: once blocked, later steps still return True."""
        return self._quyet_dinh_chan is not None

    def ly_do_chan(self) -> QuyetDinh | None:
        return self._quyet_dinh_chan

    def dat_lai(self) -> None:
        """Wipe the counters. Call at the start of a new RUN inside the same turn (retry of an empty
        completion, rebuilding the input without pixels): a new run is a new context, it must not carry the
        sins of the previous one."""
        self._dem_loi_giong_het.clear()
        self._dem_cung_tool_loi.clear()
        self._dem_khong_tien_trien.clear()
        self._quyet_dinh_chan = None

    def ghi_nhan(self, step: RawStep) -> QuyetDinh:
        """Record a step that just ran, returns the MOST SEVERE decision of that step."""
        nang = CHO_QUA

        def nhan(q: QuyetDinh, nang_hien_tai: QuyetDinh) -> QuyetDinh:
            if q.muc == "chan" and self._quyet_dinh_chan is None:
                self._quyet_dinh_chan = q
            # Keep the FIRST one in both places. The previous version took the first for
            # ``quyet_dinh_chan`` but the LAST for the return value, so a step with two tools reaching the
            # threshold gave two log lines naming two different tools for the same event: exactly the kind
            # of mismatch that wastes time when tracing a fault.
            if nang_hien_tai.muc == "cho-qua" or (q.muc == "chan" and nang_hien_tai.muc == "canh-bao"):
                return q
            return nang_hien_tai

        for p in step.content:
            if p.type != "tool-error" or not p.tool_name:
                continue
            nang = nhan(self._dem_loi(p.tool_name, p.input), nang)
        for r in step.tool_results:
            if not r.tool_name:
                continue
            # A result marked as failed goes into the ERROR counter, not the "no progress" one. The two
            # branches are cured differently, and mixing them up even yields a diagnosis pointing the wrong
            # way: ``web_fetch`` dead on the same URL 5 times was once reported as "returned the same
            # result, calling more brings nothing new" - read as if the page were alive and merely dull.
            if la_ket_qua_loi(r.output):
                nang = nhan(self._dem_loi(r.tool_name, r.input), nang)
                continue
            nang = nhan(self._dem_ket_qua(r.tool_name, r.input, r.output), nang)
        return nang

    def _dem_loi(self, ten_tool: str, args: object) -> QuyetDinh:
        chu_ky = chu_ky_lenh_goi(ten_tool, args)

        n_giong_het = self._dem_loi_giong_het.get(chu_ky, 0) + 1
        self._dem_loi_giong_het[chu_ky] = n_giong_het
        n_cung_tool = self._dem_cung_tool_loi.get(ten_tool, 0) + 1
        self._dem_cung_tool_loi[ten_tool] = n_cung_tool

        if n_giong_het >= self._nguong.chan_loi_giong_het:
            return QuyetDinh(
                muc="chan",
                ma="loi-giong-het",
                tool=ten_tool,
                so_lan=n_giong_het,
                thong_diep=(
                    f"{ten_tool} lỗi {n_giong_het} lần với ĐÚNG một bộ tham số - thử lại y hệt là vô vọng."
                ),
            )
        if n_cung_tool >= self._nguong.chan_cung_tool_loi:
            return QuyetDinh(
                muc="chan",
                ma="cung-tool-loi",
                tool=ten_tool,
                so_lan=n_cung_tool,
                thong_diep=(
                    f"{ten_tool} lỗi {n_cung_tool} lần trong một lượt "
                    "(cộng dồn, không tính có xen kẽ lần chạy được hay không)."
                ),
            )
        if n_giong_het >= canh_bao_tu(self._nguong.chan_loi_giong_het):
            return QuyetDinh(
                muc="canh-bao",
                ma="loi-giong-het",
                tool=ten_tool,
                so_lan=n_giong_het,
                thong_diep=f"{ten_tool} đã lỗi {n_giong_het} lần với cùng tham số.",
            )
        return CHO_QUA

    def _dem_ket_qua(self, ten_tool: str, args: object, ket_qua: object) -> QuyetDinh:
        # Only READ tools get this rule. A write tool called twice with the same result is legitimate
        # (sending 2 identical files, dropping 2 identical reactions).
        if not self._la_tool_doc(ten_tool):
            return CHO_QUA

        chu_ky = chu_ky_lenh_goi(ten_tool, args)
        bam_kq = bam_ngan(chuan_hoa_json(None if ket_qua is None else ket_qua))
        truoc = self._dem_khong_tien_trien.get(chu_ky)
        n = truoc[1] + 1 if truoc is not None and truoc[0] == bam_kq else 1
        self._dem_khong_tien_trien[chu_ky] = (bam_kq, n)

        if n >= self._nguong.chan_khong_tien_trien:
            return QuyetDinh(
                muc="chan",
                ma="khong-tien-trien",
                tool=ten_tool,
                so_lan=n,
                thong_diep=f"{ten_tool} trả về CÙNG một kết quả {n} lần - gọi thêm không có gì mới.",
            )
        if n >= canh_bao_tu(self._nguong.chan_khong_tien_trien):
            return QuyetDinh(
                muc="canh-bao",
                ma="khong-tien-trien",
                tool=ten_tool,
                so_lan=n,
                thong_diep=f"{ten_tool} đã trả cùng kết quả {n} lần.",
            )
        return CHO_QUA
