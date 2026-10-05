# ported from: src/knowledge/kb-extract-worker.ts
"""Body of the extraction worker of the knowledge base - RUNS IN ITS OWN PROCESS, started by
``chay_trich_xuat_tach_luong`` as ``python -m pema.knowledge.kb_extract_worker``. Mandatory invariant to
keep: NO database connection is opened here (the worker only extracts and chunks, the caller writes to the
database after it receives the result). This module imports only PURE modules (``chunk_text``,
``doc_text_extract``) - no ``pema.core.db``, no settings.

Forced deviation (``worker_threads`` -> a child process): a Python thread cannot be killed from outside
and the GIL means a CPU-bound thread would starve the event loop of the caller; only a PROCESS can be cut
at the timeout and have its memory ceiling enforced. ``workerData`` / ``postMessage`` become the child's
stdin / stdout:

* stdin  = ONE line of JSON ``{"dinh_dang", "co_doan_toi_da", "chong_lan", "tran_ram_mb"}`` then the RAW
  bytes of the file;
* stdout = ONE JSON document ``{"ok": true, "chu", "doan": [...]}`` or ``{"ok": false, "loi"}`` (an
  ordinary extraction error: broken file, unknown format, no text), or ``{"ok": false, "ngat"}`` (the
  worker itself ran out of memory: the caller treats it as "stopped midway", not as a broken document).

An ordinary extraction error is packed into a string and SENT BACK, never allowed to crash the process: the
caller must be able to tell a CONTENT error from a worker that DIED abnormally, two cases that need
different handling (see ``chay_trich_xuat_tach_luong``).

The memory ceiling is applied here, to the process itself, AFTER the input is read: ``tran_ram_mb`` is how
much the extraction may GROW the memory of the process. POSIX: ``RLIMIT_AS``. Windows: a Job Object with a
per-process commit limit. Best effort, like the original (a ceiling that "usually" turns an out-of-memory
into a catchable error but is not guaranteed, and does not bound memory outside the interpreter heap).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, BinaryIO

from pema.knowledge.chunk_text import ThamSoCat, cat_thanh_doan
from pema.knowledge.doc_text_extract import doc_chu_tu_file, la_dinh_dang_ho_tro

_MB = 1024 * 1024


def _dat_tran_ram(tran_ram_mb: int) -> None:
    """Cap the memory GROWTH of this process by ``tran_ram_mb``. Silent when the platform refuses (the
    timeout is still the first breaker)."""
    if sys.platform == "win32":
        _dat_tran_ram_windows(tran_ram_mb * _MB)
        return
    try:
        import resource  # POSIX only

        with open("/proc/self/statm", encoding="ascii") as statm:
            hien_tai = int(statm.read().split()[0]) * os.sysconf("SC_PAGE_SIZE")
        resource.setrlimit(resource.RLIMIT_AS, (hien_tai + tran_ram_mb * _MB, resource.RLIM_INFINITY))
    except (ImportError, OSError, ValueError):
        return


def _dat_tran_ram_windows(them_byte: int) -> None:  # pragma: no cover - exercised on Windows only
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("r_ops", "w_ops", "o_ops", "r_b", "w_b", "o_b")]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]

    tien_trinh = kernel32.GetCurrentProcess()
    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    if not kernel32.K32GetProcessMemoryInfo(tien_trinh, ctypes.byref(counters), counters.cb):
        return

    job_object_limit_process_memory = 0x00000100
    job_object_extended_limit_information = 9
    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = job_object_limit_process_memory
    info.ProcessMemoryLimit = counters.PrivateUsage + them_byte
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    if not kernel32.SetInformationJobObject(
        job, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)
    ):
        return
    kernel32.AssignProcessToJobObject(job, tien_trinh)


def chay(stdin: BinaryIO, stdout: BinaryIO) -> None:
    """Read one job from ``stdin``, write one result to ``stdout``."""
    try:
        dau = json.loads(stdin.readline())
        buf = stdin.read()
        dinh_dang = str(dau["dinh_dang"])
        if not la_dinh_dang_ho_tro(dinh_dang):
            raise ValueError(f'Định dạng "{dinh_dang}" chưa được hỗ trợ')
        tran_ram_mb = int(dau.get("tran_ram_mb") or 0)
        if tran_ram_mb > 0:
            _dat_tran_ram(tran_ram_mb)
        tham_so_cat = ThamSoCat(co_doan_toi_da=int(dau["co_doan_toi_da"]), chong_lan=int(dau["chong_lan"]))
        chu = doc_chu_tu_file(buf, dinh_dang)
        doan = cat_thanh_doan(chu, tham_so_cat)
        ket_qua: dict[str, Any] = {
            "ok": True,
            "chu": chu,
            "doan": [{"thu_tu": d.thu_tu, "tieu_de": d.tieu_de, "noi_dung": d.noi_dung} for d in doan],
        }
        du_lieu = json.dumps(ket_qua, ensure_ascii=False).encode("utf-8")
    except MemoryError:
        # Ran past the memory ceiling: NOT a verdict on the document (the machine may simply be tight) - the
        # caller must not mark it "hong" at once.
        du_lieu = json.dumps({"ok": False, "ngat": "MemoryError: out of memory"}).encode("utf-8")
    except Exception as err:
        loi = str(err) or type(err).__name__
        du_lieu = json.dumps({"ok": False, "loi": loi}, ensure_ascii=False).encode("utf-8")
    stdout.write(du_lieu)
    stdout.flush()


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    # Anything a library prints must not corrupt the result channel.
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    chay(stdin, stdout)


if __name__ == "__main__":
    main()
