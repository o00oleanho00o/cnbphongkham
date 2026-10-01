# ported from: src/knowledge/chay-trich-xuat-tach-luong.ts
"""Run extraction + chunking in a SEPARATE worker, with NO database connection (the worker only extracts and
chunks; the caller writes to the database after it receives the result).

TWO breakers for TWO kinds of hostile document - both are needed:

1. CPU (``han_ms`` + kill): putting a timeout on SYNCHRONOUS code that is spinning the CPU on the SAME
   thread cannot be done - a timeout is only examined at event-loop boundaries, and a synchronous loop never
   yields one until it finishes. Killing the worker is the ONLY real way to stop it. Do not try the
   timeout-on-the-same-thread direction again.

2. RAM (``tran_ram_mb``): a time ceiling does NOT stop a document that bloats memory FAST - it dies before
   ``han_ms`` arrives. See ``TRAN_RAM_WORKER_MB`` below.

Forced deviation (``node:worker_threads`` -> a child PROCESS): see ``kb_extract_worker`` for why a Python
thread cannot play this role. The caller is ``async``; the blocking wait runs in a thread of the default
executor, so the event loop is never held, and the child is killed at the timeout. A plain
``subprocess.Popen`` (not ``asyncio.create_subprocess_exec``) is used on purpose: the event loop policy of
the API/worker on Windows is the selector loop (psycopg), which cannot run subprocesses.

The original's "small buffer sharing an ArrayBuffer pool with other buffers" trap (transferring a pooled
buffer detached the pool) does not exist here: the bytes are COPIED into the child through a pipe.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Final

from pema.knowledge.chunk_text import DoanMoi, ThamSoCat
from pema.knowledge.doc_text_extract import DinhDangKb


@dataclass(frozen=True, slots=True)
class KetQuaTrichXuat:
    chu: str
    doan: list[DoanMoi]


TRAN_RAM_WORKER_MB: Final = 192
"""Default memory ceiling for the extraction worker, used when the caller does not pass ``tran_ram_mb`` (every
real code path passes ``KB_EXTRACT_MAX_RAM_MB`` from the tuning; this constant is the safety net for tests
and direct calls).

Why it MUST be set: without it a hostile document can grow the worker to whatever the machine has.
Semantics here (different from the Node ``resourceLimits`` the number came from, same intent): how many MB
the extraction may GROW the memory of the worker process beyond the interpreter it starts with. Real text
is capped at 8 MB of characters and an entry at 32 MB of XML (``ooxml_limits``), so 192 MB of growth is
ample for a legitimate document.

TWO LIMITS to know before trusting this breaker (same spirit as the original):
1. It does NOT guarantee a catchable error. Usually the allocation fails with ``MemoryError`` and the worker
   reports "stopped midway"; but on a platform that refuses to set the ceiling the timeout is the only
   breaker left. Never write anywhere that this ceiling turns an out-of-memory into a catchable error.
2. It only bounds what the OS counts for the process (address space on POSIX, commit charge on Windows);
   memory that a native library allocates in a way the OS limit cannot refuse is out of its reach. The PDF
   path (``pypdf``) is pure Python and therefore inside it."""


class LoiTrichXuatBiNgatGiuaChung(Exception):  # noqa: N818 - original class name, kept for the port map
    """The worker was forced to stop HALFWAY (past ``han_ms``, or it died abnormally - out of memory, killed)
    - unlike an ordinary extraction error (broken file, ``ok: false`` from the worker itself). In this case
    we DO NOT KNOW whether the document is truly broken or the machine was just slow/short of memory, so the
    caller (``kb_ingest_worker``) must NOT mark it "hong" at once - it must leave ``dang_xu_ly`` and let
    ``go_nguon_ket_dau_tick`` (which reads ``attempts``, runs at the start of each tick) decide to retry or
    give up. See the head of that file."""


MODULE_WORKER: Final = "pema.knowledge.kb_extract_worker"


def khoi_dong_tien_trinh() -> subprocess.Popen[bytes]:
    """Start the child. One place, so a test can observe the process it started."""
    return subprocess.Popen(  # noqa: S603 - fixed argv, sys.executable and a module of this package
        [sys.executable, "-m", MODULE_WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def _chay_dong_bo(
    buf: bytes,
    dinh_dang: DinhDangKb,
    tham_so_cat: ThamSoCat,
    han_ms: int,
    tran_ram_mb: int,
) -> KetQuaTrichXuat:
    dau = json.dumps(
        {
            "dinh_dang": dinh_dang,
            "co_doan_toi_da": tham_so_cat.co_doan_toi_da,
            "chong_lan": tham_so_cat.chong_lan,
            "tran_ram_mb": tran_ram_mb,
        }
    ).encode("utf-8")
    tien_trinh = khoi_dong_tien_trinh()
    try:
        ra, _ = tien_trinh.communicate(input=dau + b"\n" + buf, timeout=han_ms / 1000)
    except subprocess.TimeoutExpired:
        # The ONLY way to stop code that is spinning the CPU - see the head of the file.
        tien_trinh.kill()
        tien_trinh.communicate()
        raise LoiTrichXuatBiNgatGiuaChung(
            f"Trích xuất quá thời gian cho phép ({han_ms}ms) - tài liệu này có thể chứa dữ liệu gây treo"
        ) from None
    except BaseException:
        tien_trinh.kill()
        tien_trinh.communicate()
        raise

    if not ra.strip():
        raise LoiTrichXuatBiNgatGiuaChung(
            f"Worker trích xuất thoát bất thường (mã {tien_trinh.returncode}) mà không trả kết quả"
        )
    try:
        msg: dict[str, Any] = json.loads(ra)
    except ValueError:
        raise LoiTrichXuatBiNgatGiuaChung(
            f"Worker trích xuất thoát bất thường (mã {tien_trinh.returncode}) mà không trả kết quả"
        ) from None

    if msg.get("ok") is True:
        return KetQuaTrichXuat(
            chu=str(msg["chu"]),
            doan=[
                DoanMoi(thu_tu=int(d["thu_tu"]), tieu_de=str(d["tieu_de"]), noi_dung=str(d["noi_dung"]))
                for d in msg["doan"]
            ],
        )
    if "ngat" in msg:
        raise LoiTrichXuatBiNgatGiuaChung(f"Worker trích xuất dừng bất thường: {msg['ngat']}")
    raise ValueError(str(msg.get("loi", "Không đọc được tài liệu")))


async def trich_xuat_tach_luong(
    *,
    buf: bytes,
    dinh_dang: DinhDangKb,
    tham_so_cat: ThamSoCat,
    han_ms: int,
    tran_ram_mb: int | None = None,
) -> KetQuaTrichXuat:
    """``tran_ram_mb``: RAM growth ceiling (MB) for the worker, default ``TRAN_RAM_WORKER_MB``. Received as
    a parameter and NOT read from ``get_tuning`` here: this module stays PURE (no environment, no database)
    so tests can import it, exactly as ``han_ms`` already does."""
    return await asyncio.to_thread(
        _chay_dong_bo,
        buf,
        dinh_dang,
        tham_so_cat,
        han_ms,
        tran_ram_mb if tran_ram_mb is not None else TRAN_RAM_WORKER_MB,
    )
