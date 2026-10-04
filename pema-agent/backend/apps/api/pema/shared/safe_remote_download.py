# ported from: src/shared/safe-remote-download.ts
"""Tải nội dung từ URL bên ngoài một cách an toàn:

- chỉ http/https, chỉ IP public (chặn SSRF - xem private_address_guard.py)
- đọc theo stream và dừng NGAY khi vượt hạn mức, không buffer hết rồi mới kiểm
  (``response.content`` nạp cả response vào RAM trước khi biết nó to cỡ nào)
- tự đi theo redirect nhưng mỗi hop đều bị kiểm lại

Forced deviations from the TypeScript original (all of them keep the guarantee, only the mechanism changes):

* ``node:http`` / ``node:https`` with a ``lookup`` hook -> ``httpx`` driven through ``GuardedTransport``, a
  transport whose ``httpcore`` NETWORK BACKEND resolves the host, vets EVERY returned address, and then
  connects to the vetted IP itself (the TLS handshake still uses the original host name for SNI and
  certificate checks). The check and the connect are one step, so a DNS answer cannot change between "checked"
  and "connected": that is the pinning that defeats DNS rebinding, equivalent to ``guardedLookup``.
* The client never reads proxy settings from the environment (``trust_env`` is off and there is no proxy): a
  proxy would resolve the target host on its side and bypass the guard.
* ``AbortSignal`` -> the small ``AbortSignal`` class below (``aborted``, ``abort()``, listeners). Aborting
  cancels the in-flight await (a handshake or a chunk read), the equivalent of Node destroying the socket.
* ``Buffer`` -> ``bytes``; ``zlib.*Sync`` with ``maxOutputLength`` -> ``zlib.decompressobj`` with
  ``max_length``; brotli needs the optional ``brotli`` package (>= 1.2, bounded output). When it is missing,
  ``br`` is not advertised in ``Accept-Encoding`` and a ``br`` body is rejected, never decoded unbounded.
* Injection points for tests (no real network, no sleeping): ``resolver`` (hostname -> addresses),
  ``transport`` (any ``httpx.AsyncBaseTransport``, e.g. ``httpx.MockTransport``) and, for
  ``GuardedTransport``, ``network_backend``. A transport you inject is NOT closed by this module.
"""

from __future__ import annotations

import asyncio
import importlib
import math
import re
import socket
import zlib
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Sequence,
)
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast
from urllib.parse import unquote, urlsplit

import httpcore
import httpx

from pema.shared.private_address_guard import hostname_to_address, is_ip, is_public_address

DEFAULT_TIMEOUT_MS = 15_000
MAX_REDIRECTS = 3

_BROWSER_HEADERS: dict[str, str] = {
    # Request trần (không header) bị nhiều site trả 403/406 - đo thực tế:
    # vnexpress 406, sjc.com.vn 403. Gửi bộ header trình duyệt tối thiểu là qua
    # được phần lớn. Site sau Cloudflare vẫn chặn - đó là việc của fallback.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    # Nhiều site nén gzip kể cả khi không được hỏi - đo được: znews.vn trả "content-encoding: gzip" với
    # request không hề khai. Vì đằng nào cũng phải giải nén, khai đủ như trình duyệt luôn: tiết kiệm băng
    # thông và bớt một tín hiệu "không phải trình duyệt". ("Accept-Encoding" is set in ``_browser_headers``
    # because ``br`` is only advertised when this process can decode it safely.)
    "Cache-Control": "no-cache",
}

LOI_DA_HUY = "Đã hủy tải (lượt hết thời gian)"
"""Lỗi khi bị HỦY qua ``AbortSignal`` (lượt agent hết ``LLM_TURN_TIMEOUT_MS`` hoặc bị dừng). Khác lỗi timeout
mạng nội bộ: đây là "lượt bỏ cuộc rồi, đừng tải nữa". Caller bắt như mọi lỗi tải khác rồi trả ``ketQuaLoi`` -
không ném ra agent loop."""


class RemoteDownloadError(Exception):
    """Every failure of this module (the original throws plain ``Error``). The message is a short Vietnamese
    text without a URL, so the caller can hand it to the LLM or the log."""


class AbortSignal:
    """Minimal ``AbortSignal``: ``aborted`` flag, ``abort()`` and one-shot listeners."""

    def __init__(self) -> None:
        self._aborted = False
        self._listeners: list[Callable[[], None]] = []

    @property
    def aborted(self) -> bool:
        return self._aborted

    def abort(self) -> None:
        if self._aborted:
            return
        self._aborted = True
        listeners, self._listeners = self._listeners, []
        for listener in listeners:
            listener()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register ``listener`` (called once on abort). Returns the function that removes it."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove


@dataclass(frozen=True)
class RemoteFile:
    data: bytes
    media_type: str
    file_name: str


@dataclass(frozen=True)
class DownloadOptions:
    max_bytes: int
    timeout_ms: int | None = None
    signal: AbortSignal | None = None


HostResolver = Callable[[str], Awaitable[Sequence[str]]]
"""hostname -> every address it resolves to (the ``dns.lookup(..., {all: true})`` of the original)."""


def _format_mb(num_bytes: int) -> str:
    # JS Math.round rounds half up; Python round() is banker's rounding, so do it by hand.
    return f"{math.floor(num_bytes / (1024 * 1024) + 0.5)}MB"


def _too_big(max_bytes: int) -> RemoteDownloadError:
    return RemoteDownloadError(f"Nội dung vượt giới hạn {_format_mb(max_bytes)}")


# --------------------------------------------------------------------------- abort helper


async def run_abortable[T](coro: Coroutine[Any, Any, T], signal: AbortSignal | None) -> T:
    """Run ``coro``; an ``abort`` cancels it (cuts a handshake or a chunk read that is waiting forever, the
    slow-drip case an idle timeout never catches) and raises ``LOI_DA_HUY``."""
    if signal is None:
        return await coro
    task: asyncio.Task[T] = asyncio.ensure_future(coro)

    def cancel() -> None:
        task.cancel()

    remove = signal.add_listener(cancel)
    try:
        return await task
    except asyncio.CancelledError:
        if signal.aborted:
            raise RemoteDownloadError(LOI_DA_HUY) from None
        raise
    finally:
        remove()


async def _close_stream(stream: object) -> None:
    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        result = aclose()
        if isinstance(result, Awaitable):
            await result


# --------------------------------------------------------------------------- guarded DNS + transport


async def system_resolver(hostname: str) -> list[str]:
    """Default resolver: the system resolver through the running loop, every distinct address."""
    infos = await asyncio.get_running_loop().getaddrinfo(
        hostname, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    seen: dict[str, None] = {}
    for info in infos:
        seen[str(info[4][0])] = None
    return list(seen)


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    """``guardedLookup``. Resolves the host, refuses the connection when ANY address is not public, and
    connects to the vetted address itself, so the socket uses exactly what was checked (no rebinding window).
    """

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver: HostResolver = resolver if resolver is not None else system_resolver
        self._inner: httpcore.AsyncNetworkBackend = (
            inner if inner is not None else cast(httpcore.AsyncNetworkBackend, httpcore.AnyIOBackend())
        )

    async def _vetted_addresses(self, hostname: str) -> list[str]:
        address = hostname_to_address(hostname)
        try:
            addresses = [address] if is_ip(address) else list(await self._resolver(hostname))
        except OSError:
            raise RemoteDownloadError(f"Không phân giải được {hostname}") from None
        blocked = next((a for a in addresses if not is_public_address(a)), None)
        if blocked is not None:
            raise RemoteDownloadError(f"Chặn địa chỉ nội bộ: {hostname} -> {blocked}")
        if not addresses:
            raise RemoteDownloadError(f"Không phân giải được {hostname}")
        return addresses

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - signature fixed by httpcore
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await self._vetted_addresses(host)
        last_error: httpcore.ConnectError | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.ConnectError as exc:
                last_error = exc
        if last_error is None:  # unreachable: _vetted_addresses never returns an empty list
            raise RemoteDownloadError(f"Không phân giải được {host}")
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - signature fixed by httpcore
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise RemoteDownloadError("Không hỗ trợ kết nối unix socket")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class GuardedTransport(httpx.AsyncHTTPTransport):
    """``httpx`` transport whose connections go through ``GuardedNetworkBackend`` (HTTP/1.1 only, no proxy,
    no environment settings, no connection reuse beyond one open request)."""

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        ssl_context = httpx.create_ssl_context(trust_env=False)
        super().__init__(verify=ssl_context, trust_env=False, http1=True, http2=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=4,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            network_backend=GuardedNetworkBackend(resolver=resolver, inner=network_backend),
        )


# --------------------------------------------------------------------------- brotli (optional)


def _load_brotli() -> Any | None:
    """The ``brotli`` module when it is installed AND can bound its output (>= 1.2), else None."""
    try:
        module = importlib.import_module("brotli")
    except ImportError:
        return None
    if not hasattr(getattr(module, "Decompressor", None), "can_accept_more_data"):
        return None
    return module


def _browser_headers() -> httpx.Headers:
    headers = httpx.Headers(_BROWSER_HEADERS)
    headers["Accept-Encoding"] = "gzip, deflate, br" if _load_brotli() is not None else "gzip, deflate"
    return headers


# --------------------------------------------------------------------------- read / decompress


async def read_capped_stream(
    stream: AsyncIterable[bytes | str],
    max_bytes: int,
    signal: AbortSignal | None = None,
) -> bytes:
    """Đọc stream với hạn mức byte. Vượt hạn thì ném lỗi và huỷ stream ngay (``aclose``) nên không tải nốt
    phần còn lại."""
    if signal is not None and signal.aborted:
        raise RemoteDownloadError(LOI_DA_HUY)

    async def read_all() -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in stream:
            data = chunk.encode() if isinstance(chunk, str) else chunk
            total += len(data)
            if total > max_bytes:
                raise _too_big(max_bytes)
            chunks.append(data)
        return b"".join(chunks)

    # Huỷ stream khi abort để BUNG vòng đọc đang chờ chunk kế. Ca nhỏ giọt (stream không tự kết thúc, chỉ
    # trả 1 byte thật chậm) thì kiểm cờ trong vòng lặp vô dụng - nó kẹt ở chunk sau; chỉ cancel mới cắt được.
    try:
        result = await run_abortable(read_all(), signal)
    finally:
        await _close_stream(stream)
    # Stream kết thúc bình thường NGAY khi abort vẫn phải báo huỷ, không trả về buffer cụt như thành công.
    if signal is not None and signal.aborted:
        raise RemoteDownloadError(LOI_DA_HUY)
    return result


def _inflate(data: bytes, wbits: int, max_bytes: int) -> bytes:
    """One zlib/gzip/raw-deflate stream with an output ceiling. Raises ``zlib.error`` on corrupt or
    truncated input and ``RemoteDownloadError`` when the output would pass ``max_bytes``."""
    out = bytearray()
    remaining = data
    while True:
        decompressor = zlib.decompressobj(wbits)
        piece = decompressor.decompress(remaining, max_bytes - len(out) + 1)
        out.extend(piece)
        if len(out) > max_bytes:
            raise RemoteDownloadError("Dữ liệu bung ra vượt giới hạn")
        if not decompressor.eof:
            raise zlib.error("unexpected end of file")
        remaining = decompressor.unused_data
        # gzip allows several members back to back; the others are single streams
        if not remaining or wbits != 31:
            return bytes(out)


def _brotli_decompress(data: bytes, max_bytes: int) -> bytes:
    module = _load_brotli()
    if module is None:
        raise RemoteDownloadError('Không giải nén được kiểu "br" (thiếu thư viện brotli)')
    decompressor = module.Decompressor()
    out = bytearray()
    out.extend(decompressor.process(data, output_buffer_limit=max_bytes + 1))
    while len(out) <= max_bytes and not decompressor.is_finished() and decompressor.can_accept_more_data():
        out.extend(decompressor.process(b"", output_buffer_limit=max_bytes - len(out) + 1))
    if len(out) > max_bytes:
        raise RemoteDownloadError("Dữ liệu bung ra vượt giới hạn")
    if not decompressor.is_finished():
        raise RemoteDownloadError("Dữ liệu brotli bị cụt")
    return bytes(out)


def decompress_body(data: bytes, content_encoding: str | None, max_bytes: int) -> bytes:
    """Giải nén body theo header ``content-encoding``.

    Lỗi thật đã gặp: znews.vn và tienphong.vn trả gzip, code cũ ``.toString("utf-8")`` thẳng vào buffer nén
    nên tool web_fetch đẩy 46.000 ký tự rác nhị phân vào context của model - vừa đốt token vừa mất luôn nguồn
    đó. Rác thì dài nên ngưỡng "quá ít chữ" cũng không kích hoạt được lưới đỡ Jina.

    ``max_bytes`` chặn zip bomb: file nén 1MB có thể bung thành hàng GB, cap ở tầng stream (dữ liệu nén)
    không cứu được.
    """
    codec = (content_encoding or "").strip().lower()
    if not codec or codec == "identity":
        return data

    try:
        if codec in ("gzip", "x-gzip"):
            return _inflate(data, 31, max_bytes)
        if codec == "br":
            return _brotli_decompress(data, max_bytes)
        if codec == "deflate":
            # Một số server gửi deflate thô (không có zlib header) - thử cả 2 kiểu
            try:
                return _inflate(data, zlib.MAX_WBITS, max_bytes)
            except zlib.error:
                return _inflate(data, -zlib.MAX_WBITS, max_bytes)
        # Trả nguyên buffer là tái diễn đúng bug cũ (rác nhị phân vào context),
        # báo lỗi để caller rơi xuống nguồn khác
        raise RemoteDownloadError(f'Không giải nén được kiểu "{codec}"')
    except (zlib.error, RemoteDownloadError) as exc:
        raise RemoteDownloadError(f"Giải nén nội dung thất bại: {exc}") from None


# --------------------------------------------------------------------------- guarded request


HeaderDocThem = TypedDict("HeaderDocThem", {"range": str, "Accept-Encoding": str}, total=False)
"""Header ĐƯỢC PHÉP thêm vào một request đã qua gác.

Danh sách CHO PHÉP, không phải dict tự do - xem chú thích ở ``open_guarded_request``. Hai header này chỉ ảnh
hưởng phần nội dung được trả về, không đụng tới danh tính hay đích đến của request. Python does not enforce
a ``TypedDict`` at run time, so ``open_guarded_request`` also rejects any other key."""

_ALLOWED_EXTRA_HEADERS = frozenset({"range", "accept-encoding"})


@contextmanager
def _map_transport_errors(timeout_ms: int) -> Generator[None]:
    try:
        yield
    except httpx.TimeoutException:
        raise RemoteDownloadError(f"Hết thời gian chờ {timeout_ms}ms") from None
    except (httpx.TransportError, httpx.InvalidURL) as exc:
        raise RemoteDownloadError(f"Lỗi kết nối ({type(exc).__name__})") from None


class GuardedResponse:
    """A streamed response that already passed the guard: ``status_code``, ``headers``, and an async
    iterator over the RAW (still compressed) body, so it can be handed to ``read_capped_stream``."""

    def __init__(
        self,
        response: httpx.Response,
        *,
        timeout_ms: int,
        owned_transport: httpx.AsyncBaseTransport | None,
    ) -> None:
        self._response = response
        self._timeout_ms = timeout_ms
        self._owned_transport = owned_transport
        self._closed = False
        self.status_code: int = response.status_code
        self.headers: httpx.Headers = response.headers

    async def __aiter__(self) -> AsyncIterator[bytes]:
        with _map_transport_errors(self._timeout_ms):
            async for chunk in self._response.aiter_raw():
                yield chunk

    async def aclose(self) -> None:
        """``res.destroy()``: drop the rest of the body and release the connection (idempotent)."""
        if self._closed:
            return
        self._closed = True
        try:
            await self._response.aclose()
        finally:
            if self._owned_transport is not None:
                await self._owned_transport.aclose()


def parse_public_url(raw_url: str) -> httpx.URL:
    """``new URL(rawUrl)``: ``RemoteDownloadError("URL không hợp lệ")`` for anything without a scheme. A
    ``file:`` or ``ftp:`` URL parses fine and is refused later with the http/https message, as in the
    original."""
    try:
        parts = urlsplit(raw_url)
        if not parts.scheme or (parts.scheme in ("http", "https") and not parts.hostname):
            raise ValueError("no scheme or host")
        return httpx.URL(raw_url)
    except (ValueError, httpx.InvalidURL):
        raise RemoteDownloadError("URL không hợp lệ") from None


async def open_guarded_request(
    url: httpx.URL,
    timeout_ms: int,
    method: Literal["GET", "HEAD"] = "GET",
    header_them: HeaderDocThem | None = None,
    signal: AbortSignal | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
) -> GuardedResponse:
    """Mở một request ĐÃ QUA GÁC tới URL công khai. The caller MUST ``await response.aclose()``.

    ``method`` và ``header_them`` mặc định giữ nguyên hành vi cũ (GET, không header thêm) để mọi caller có sẵn
    không đổi gì.

    ``header_them`` cố ý CHỈ nhận vài header đọc-thêm, không nhận dict tự do: một dict tự do ghi đè được cả
    ``Host``, ``Cookie``, ``Authorization`` (đã đo trên dây với Node: caller cung cấp ``Host`` thì Node bỏ
    hẳn Host tự sinh, và còn cho gửi đồng thời ``content-length`` + ``transfer-encoding: chunked``). Hôm nay
    chưa caller nào đưa dữ liệu ngoài vào đây, nhưng một tham số hình dạng tự do là lời mời cho lần sau.

    ĐỪNG DÙNG ``"HEAD"`` ĐỂ DÒ XEM URL CÒN SỐNG - đã đo và trả giá: CDN của TikTok trả **503 cho HEAD nhưng
    206 cho GET kèm ``Range``** trên cùng một URL, và điều đó khác nhau theo từng host
    (``v19.tiktokcdn-us.com`` trả lời HEAD bình thường, ``v16m.tiktokcdn-us.com`` thì không). Dò bằng HEAD là
    đẩy oan những video hoàn toàn sống sang đường dự phòng đắt nhất. Dùng GET kèm ``Range: bytes=0-0``: đúng
    cách máy người nhận sẽ tải, mà chỉ tốn một byte.

    ``transport`` / ``resolver``: injection points (see the module docstring). Without ``transport`` a
    ``GuardedTransport`` is built here and closed with the response.
    """
    if url.scheme not in ("http", "https"):
        raise RemoteDownloadError(f'Chỉ hỗ trợ http/https, không hỗ trợ "{url.scheme}:"')

    # URL ghi thẳng IP thì socket bỏ qua bước DNS -> bước vet trong network backend không có gì để phân giải,
    # nên kiểm sớm ở đây (cũng để một transport do test tiêm vào không thể nuốt "http://127.0.0.1:3900").
    address = hostname_to_address(url.raw_host.decode("ascii"))
    if is_ip(address) and not is_public_address(address):
        raise RemoteDownloadError(f"Chặn địa chỉ nội bộ: {address}")

    headers = _browser_headers()
    for key, value in cast("dict[str, str]", header_them or {}).items():
        if key.lower() not in _ALLOWED_EXTRA_HEADERS:
            raise ValueError(f'Header không được phép: "{key}"')
        headers[key] = value

    owned = transport is None
    use_transport: httpx.AsyncBaseTransport = (
        GuardedTransport(resolver=resolver) if transport is None else transport
    )
    request = httpx.Request(
        method,
        url,
        headers=headers,
        # idle timeout (connect / read / write / pool), the ``timeout`` option of node:http; ``signal`` is the
        # second layer
        extensions={
            "timeout": {
                "connect": timeout_ms / 1000,
                "read": timeout_ms / 1000,
                "write": timeout_ms / 1000,
                "pool": timeout_ms / 1000,
            }
        },
    )

    async def send() -> httpx.Response:
        with _map_transport_errors(timeout_ms):
            response = await use_transport.handle_async_request(request)
        response.request = request
        return response

    try:
        response = await run_abortable(send(), signal)
    except BaseException:
        if owned:
            await use_transport.aclose()
        raise
    return GuardedResponse(response, timeout_ms=timeout_ms, owned_transport=use_transport if owned else None)


_UNSAFE_NAME_CHARS = re.compile(r"[^a-zA-Z0-9._-]")


def _file_name_from_url(url: httpx.URL) -> str:
    """Tên file gợi ý từ URL, đã lọc ký tự để dùng làm tên file trên đĩa."""
    last = url.raw_path.split(b"?", 1)[0].decode("ascii", errors="replace").rsplit("/", 1)[-1]
    try:
        raw = unquote(last, errors="strict")
    except UnicodeDecodeError:
        raw = last
    safe = _UNSAFE_NAME_CHARS.sub("_", raw).lstrip(".")[:120]
    return safe or "tep-tai-ve"


async def download_from_public_url(
    raw_url: str,
    options: DownloadOptions,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
) -> RemoteFile:
    """Ném ``RemoteDownloadError`` với thông báo tiếng Việt gọn - caller đưa thẳng cho LLM/log được."""
    url = parse_public_url(raw_url)
    timeout_ms = options.timeout_ms if options.timeout_ms is not None else DEFAULT_TIMEOUT_MS

    for _hop in range(MAX_REDIRECTS + 1):
        if options.signal is not None and options.signal.aborted:
            raise RemoteDownloadError(LOI_DA_HUY)
        res = await open_guarded_request(
            url, timeout_ms, "GET", None, options.signal, transport=transport, resolver=resolver
        )
        try:
            status = res.status_code
            location = res.headers.get("location")

            if 300 <= status < 400 and location:
                try:
                    url = url.join(location)  # hop mới đi qua guard ở vòng lặp sau
                except httpx.InvalidURL:
                    raise RemoteDownloadError("URL không hợp lệ") from None
                continue

            if status < 200 or status >= 300:
                raise RemoteDownloadError(f"HTTP {status}")

            # Có Content-Length thì chặn trước khi đọc byte nào
            declared = _parse_number(res.headers.get("content-length"))
            if declared is not None and declared > options.max_bytes:
                raise _too_big(options.max_bytes)

            raw = await read_capped_stream(res, options.max_bytes, options.signal)
            if len(raw) == 0:
                raise RemoteDownloadError("Nội dung rỗng")

            # Giải nén TRƯỚC khi trả về: caller nào cũng đang coi đây là dữ liệu thô
            data = decompress_body(raw, res.headers.get("content-encoding"), options.max_bytes)

            content_type = res.headers.get("content-type")
            if content_type is None:
                content_type = "application/octet-stream"
            return RemoteFile(
                data=data,
                media_type=content_type.split(";")[0].strip(),
                file_name=_file_name_from_url(url),
            )
        finally:
            await res.aclose()

    raise RemoteDownloadError(f"Quá {MAX_REDIRECTS} lần chuyển hướng")


def _parse_number(value: str | None) -> float | None:
    """``Number(value)`` kept only when ``Number.isFinite`` (a missing / junk header means 'unknown')."""
    if value is None:
        return None
    try:
        number = float(value.strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None
