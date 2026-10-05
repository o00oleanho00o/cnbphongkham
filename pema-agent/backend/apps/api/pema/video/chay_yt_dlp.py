# ported from: src/video/chay-yt-dlp.ts
"""The ONE place that knows how to run the yt-dlp process safely.

There are two ways to use yt-dlp: reading metadata (``nguon_yt_dlp``) and downloading the file itself
(``tai_video_vao_ram``). If each side called the subprocess on its own, the hardening layer would live in two
places, and the one forgotten when editing is always the one fewer people read: the lesson recorded for
``openGuardedRequest``.

Three hardening layers, each with a measured reason:

1. ``env_toi_thieu``: an ALLOW-LIST of environment variables. This process parses the content of a URL sent
   by a STRANGER, so it has no business seeing ``CREDENTIALS_ENCRYPTION_KEY`` or the router API key. An
   allow-list (not a deny-list) so a secret variable added later is automatically left out.

2. ``--ignore-config``: drop every config file (``yt-dlp.conf`` in the working directory, the home
   directory, /etc). Such a file can set ``--exec``, i.e. run an arbitrary command. Checked both ways: put a
   junk config into the working directory and run WITHOUT the flag and yt-dlp says ``no such option`` (so it
   DOES read it); run WITH the flag and it is ignored cleanly.

3. ``--no-plugin-dirs``: load no plugin. A plugin is Python code running inside this very process. Checked:
   ``Plugin directories: none (disabled)``.

Both (2) and (3) are escalation paths from "can write a file" to "can run a command", and the bot has a
tool that writes files.

Forced deviations: Node ``execFile`` becomes an asyncio subprocess started with an ARGUMENT LIST and no
shell (there is no place for command injection, and the URL that reaches here already went through the
whitelist so it cannot be a string starting with ``-`` read as a flag); ``Buffer`` becomes ``bytes``;
``maxBuffer`` is enforced by reading the pipes with a cap and killing the child when it is exceeded; the
original ``env`` import (``config/env.ts``) becomes ``os.environ.get`` of the SAME variable names
(``YTDLP_PATH``, ``PYTHON_PATH``), which are not tuning parameters. ``NodeJS.ErrnoException`` becomes the
two things the check really reads: an error code (``"ENOENT"`` or an exit code) and the stderr text.

On Windows the project runs a selector event loop (psycopg needs it) and that loop cannot start
subprocesses; the spawn then retries in a worker thread with its own proactor loop. On Ubuntu (production)
that branch never runs.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field

TRAN_STDOUT = 8 * 1024 * 1024
"""Ceiling of the text read from stdout: the yt-dlp JSON can be a few hundred KB for a video with many
formats."""

CO_AN_TOAN: tuple[str, ...] = ("--ignore-config", "--no-plugin-dirs")
"""Mandatory flags for EVERY yt-dlp call. See the module docstring.

They stand at the head of the command line, before any caller argument, so nobody can slip anything in front
of them."""

LOI_THIEU_YTDLP = (
    "Máy chủ chưa cài yt-dlp nên không đọc được video này (Facebook cần nó, TikTok mất tầng dự phòng). "
    "Đây là thiếu sót cấu hình máy chủ, KHÔNG phải video có vấn đề - nói đúng như vậy với người dùng."
)
"""Own error text for the MISSING TOOL case: it must be clearly different from a video error.

This string goes into the sentence the tool returns to the model, so it must be enough for the operator to
know where to fix it without opening the log."""

ENV_CHO_PHEP: tuple[str, ...] = (
    "PATH",
    "Path",
    "SystemRoot",
    "SYSTEMROOT",
    "windir",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CACHE_HOME",
    "LANG",
    "LC_ALL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
"""Environment variables ALLOWED into the yt-dlp process. Every one is really needed:

* PATH/Path        - find python itself (Windows uses ``Path``)
* SystemRoot       - Python on Windows does NOT start without it
* TEMP/TMP/TMPDIR  - where temp files go
* HOME/USERPROFILE - yt-dlp looks for its cache directory here
* APPDATA          - MEASURED on a dev machine: without it Python drops the user site-packages directory,
                     a ``pip install --user`` install vanishes and reports ``No module named yt_dlp``
                     exactly like the not-installed case. Docker installs system-wide so it is not hit, but
                     the symptom points completely the wrong way.
* LOCALAPPDATA / XDG_CACHE_HOME - cache directory
* LANG/LC_ALL      - avoid encoding errors printing accented titles
* *_PROXY/NO_PROXY - a VPS with an egress firewall usually forces a proxy; without this group yt-dlp cannot
                     reach the network in exactly the most locked-down environment. These are config URLs,
                     not secrets.

DELIBERATELY NOT let through: ``PYTHONPATH`` and ``PYTHONSTARTUP``: both load Python code into this process,
so they are exactly what an allow-list exists to block. (The project's ``PYTHON_PATH`` differs from
``PYTHONPATH`` by one underscore, do not misread it.)
"""


def env_toi_thieu() -> dict[str, str]:
    ra: dict[str, str] = {
        # Force UTF-8: TikTok/Facebook titles are full of emoji and accented letters, and Python on Windows
        # defaults to cp1252 which would RAISE when printing them.
        "PYTHONIOENCODING": "utf-8",
    }
    for ten in ENV_CHO_PHEP:
        v = os.environ.get(ten)
        if v is not None:
            ra[ten] = v
    return ra


@dataclass(frozen=True)
class _LenhYtDlp:
    file: str
    dau_vao: list[str]


def lenh_yt_dlp() -> _LenhYtDlp:
    """How yt-dlp is run. Configurable because Docker and a dev machine put it in different places."""
    tu_env = (os.environ.get("YTDLP_PATH") or "").strip()
    if tu_env:
        return _LenhYtDlp(file=tu_env, dau_vao=[])
    # ``python -m yt_dlp`` also works when there is no ``yt-dlp`` binary in PATH: the case of a pip install
    # inside the Docker image.
    python = (os.environ.get("PYTHON_PATH") or "").strip() or "python"
    return _LenhYtDlp(file=python, dau_vao=["-m", "yt_dlp"])


@dataclass(frozen=True)
class KetQuaChayYtDlp:
    """``KetQuaChayYtDlp``: ``{ok: true, stdout, stdoutNhiPhan?}`` or ``{ok: false, loi, loiCauHinh?}``."""

    ok: bool
    stdout: str = ""
    stdout_nhi_phan: bytes | None = None
    loi: str = ""
    loi_cau_hinh: bool = False


@dataclass(frozen=True)
class TuyChonChay:
    nhi_phan: bool = False
    """Receive stdout as BINARY instead of text.

    For ``-o -`` (yt-dlp writes the video straight to stdout). Forcing it to text corrupts binary data: every
    byte invalid in UTF-8 becomes a replacement character and the file no longer opens."""
    tran_stdout: int | None = None
    """Ceiling of the stdout buffer. The default is enough for metadata JSON, a video download needs far
    more."""


def la_loi_thieu_cong_cu(code: str | int | None, stderr: str) -> bool:
    """yt-dlp is on the machine but runs broken because the TOOL is missing, not because of the video?

    Two shapes, and the second is the real Docker case:

    * ``ENOENT``: the binary itself is missing (``python3`` / ``yt-dlp``). On Docker ``apk add python3``
      guarantees it, so this is almost only a dev-machine case.
    * Exit code 1 with stderr ``No module named yt_dlp``: ``python3`` exists but NOT the module. This is the
      production case (broken pip install, changed base image, a package removed by mistake). MEASURED:
      the error code is 1, NOT "ENOENT", so a branch that catches only ENOENT misses exactly the case
      that most needs catching, and the model gets "the video may be private".

    ``code`` replaces ``err.code`` of ``NodeJS.ErrnoException``: ``"ENOENT"`` or the exit code.
    """
    if code == "ENOENT":
        return True
    return re.search(r"No module named ['\"]?yt[_-]?dlp", stderr, re.IGNORECASE) is not None


@dataclass(frozen=True)
class LoiGoi:
    file: str
    doi_so: list[str]
    env: dict[str, str]


def dung_loi_goi(doi_so: list[str]) -> LoiGoi:
    """Build the final call. PURE, split out so it can be tested.

    Without the split the three hardening layers of this file have NOTHING watching them: measured, dropping
    ``CO_AN_TOAN`` from the command line, or changing ``env_toi_thieu()`` to the whole environment, kept the
    whole suite green. ``env_toi_thieu`` is tested hard AS A FUNCTION, but nobody measured whether it is
    USED, and deleting one word there lets ``CREDENTIALS_ENCRYPTION_KEY`` flow into the process that parses a
    stranger's URL.
    """
    lenh = lenh_yt_dlp()
    # ``CO_AN_TOAN`` stands BEFORE the caller's arguments: nobody can slip anything in front of them.
    return LoiGoi(file=lenh.file, doi_so=[*lenh.dau_vao, *CO_AN_TOAN, *doi_so], env=env_toi_thieu())


@dataclass(frozen=True)
class TuyChonExec:
    """Options of the subprocess (``tuyChonExec``). ``encoding`` is ``"buffer"`` or ``None``."""

    timeout: int
    max_buffer: int
    env: dict[str, str] = field(default_factory=lambda: {})
    encoding: str | None = None


def tuy_chon_exec(tran_ms: int, env: dict[str, str], tuy_chon: TuyChonChay) -> TuyChonExec:
    """Build the options for the subprocess. PURE, split out so it can be tested.

    The most worth guarding here is ``encoding="buffer"`` when taking BINARY stdout (``-o -`` makes yt-dlp
    write the video straight to stdout). Without it the byte stream is forced to a UTF-8 string, every
    invalid byte becomes a replacement character, and the file received DOES NOT OPEN: a silent failure,
    since everything else still runs normally.
    """
    return TuyChonExec(
        timeout=tran_ms,
        max_buffer=tuy_chon.tran_stdout if tuy_chon.tran_stdout is not None else TRAN_STDOUT,
        env=env,
        # stderr must still be read as text to recognise errors: converted at the receiving end.
        encoding="buffer" if tuy_chon.nhi_phan else None,
    )


class _TranBufferError(Exception):
    """Internal: a pipe went over ``maxBuffer``."""


async def _doc_ong(stream: asyncio.StreamReader | None, tran: int) -> bytes:
    if stream is None:
        return b""
    out = bytearray()
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            return bytes(out)
        out += chunk
        if len(out) > tran:
            raise _TranBufferError


_KetQuaTho = tuple[int | None, bytes, bytes, str]
"""``(exit_code, stdout, stderr, kill)`` where ``kill`` is ``""``, ``"timeout"`` or ``"buffer"``."""


async def _chay_tien_trinh(lenh: LoiGoi, tc: TuyChonExec) -> _KetQuaTho:
    """Spawn, read both pipes with a cap, wait with a deadline. Raises ``OSError`` for ENOENT and friends."""
    proc = await asyncio.create_subprocess_exec(
        lenh.file,
        *lenh.doi_so,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=lenh.env,
    )
    try:
        out, err = await asyncio.wait_for(
            asyncio.gather(_doc_ong(proc.stdout, tc.max_buffer), _doc_ong(proc.stderr, tc.max_buffer)),
            timeout=tc.timeout / 1000,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None, b"", b"", "timeout"
    except _TranBufferError:
        proc.kill()
        await proc.wait()
        return None, b"", b"", "buffer"
    code = await proc.wait()
    return code, out, err, ""


async def _chay_voi_du_phong_windows(lenh: LoiGoi, tc: TuyChonExec) -> _KetQuaTho:
    try:
        return await _chay_tien_trinh(lenh, tc)
    except NotImplementedError:
        if sys.platform != "win32":
            raise

    # Selector loop (psycopg policy) cannot spawn on Windows: run in a thread with a proactor loop.
    def _chay() -> _KetQuaTho:
        loop_factory = getattr(asyncio, "ProactorEventLoop")  # noqa: B009
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            return runner.run(_chay_tien_trinh(lenh, tc))

    return await asyncio.to_thread(_chay)


async def chay_yt_dlp(
    doi_so: list[str], tran_ms: int, tuy_chon: TuyChonChay | None = None
) -> KetQuaChayYtDlp:
    """Run yt-dlp with the caller's arguments. NEVER raises: every failing branch returns ``ok=False``.

    The arguments go as a LIST (no shell) so there is no room for command injection; and the URL that reaches
    here already went through the whitelist so it cannot be a string starting with ``-`` read as a flag.
    """
    opts = tuy_chon or TuyChonChay()
    lenh = dung_loi_goi(doi_so)
    tc = tuy_chon_exec(tran_ms, lenh.env, opts)
    try:
        code, stdout_tho, stderr_tho, kill = await _chay_voi_du_phong_windows(lenh, tc)
    except FileNotFoundError:
        return KetQuaChayYtDlp(ok=False, loi=LOI_THIEU_YTDLP, loi_cau_hinh=True)
    except OSError as exc:
        return KetQuaChayYtDlp(ok=False, loi=f"không chạy được yt-dlp ({exc.errno})"[:300])

    # The process was KILLED: ``killed`` is on in TWO cases, a deadline and a buffer overflow. They are told
    # apart by the cause: merging the two would say "over 300000ms" for an error unrelated to time and send
    # the debugger the wrong way.
    if kill == "timeout":
        return KetQuaChayYtDlp(ok=False, loi=f"yt-dlp quá {tran_ms}ms, đã dừng")
    if kill == "buffer":
        return KetQuaChayYtDlp(ok=False, loi="yt-dlp in ra quá nhiều, đã dừng")
    if code != 0:
        stderr = stderr_tho.decode("utf-8", errors="replace")
        if la_loi_thieu_cong_cu(code, stderr):
            return KetQuaChayYtDlp(ok=False, loi=LOI_THIEU_YTDLP, loi_cau_hinh=True)
        doan_loi = next((d for d in stderr.split("\n") if d.startswith("ERROR:")), f"yt-dlp thoát mã {code}")
        return KetQuaChayYtDlp(ok=False, loi=doan_loi[:300])
    if opts.nhi_phan:
        return KetQuaChayYtDlp(ok=True, stdout="", stdout_nhi_phan=bytes(stdout_tho))
    return KetQuaChayYtDlp(ok=True, stdout=stdout_tho.decode("utf-8", errors="replace"))
