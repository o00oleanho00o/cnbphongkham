# ported from: src/shared/safe-remote-download.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original cases come first, in the original order. The tests after the marker ``# ---- added`` are NOT in
the TypeScript suite: they cover what Node's ``guardedLookup`` / ``http.request`` gave for free and what the
httpx port has to prove (pinned connection, vetting of every address, redirect hops, caps), with the injected
resolver, ``httpx.MockTransport`` and an in-memory network backend: no real network, no sleeping.
"""

from __future__ import annotations

import asyncio
import gzip
import importlib.util
import zlib
from collections.abc import AsyncIterator, Coroutine, Iterable
from typing import Any

import httpcore
import httpx
import pytest

from pema.shared import safe_remote_download as srd
from pema.shared.safe_remote_download import (
    AbortSignal,
    DownloadOptions,
    GuardedTransport,
    RemoteDownloadError,
    decompress_body,
    download_from_public_url,
    open_guarded_request,
    parse_public_url,
    read_capped_stream,
)


class FakeReadable:
    """The ``Readable.from(chunks)`` of the original: an async iterable with a ``destroyed`` flag."""

    def __init__(self, *chunks: bytes) -> None:
        self._chunks = list(chunks)
        self.destroyed = False

    def __aiter__(self) -> FakeReadable:
        return self

    async def __anext__(self) -> bytes:
        if self.destroyed or not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:
        self.destroyed = True


class NeverEndingReadable:
    """``new Readable({ read() {} })``: never yields, never ends; only closing or cancelling cuts it."""

    def __init__(self) -> None:
        self.destroyed = False

    def __aiter__(self) -> NeverEndingReadable:
        return self

    async def __anext__(self) -> bytes:
        await asyncio.Event().wait()
        raise StopAsyncIteration

    async def aclose(self) -> None:
        self.destroyed = True


# ------------------------------------------------------------------ readCappedStream


async def test_read_capped_stream_reads_whole_stream_within_cap() -> None:
    """đọc hết stream khi trong hạn mức"""
    data = await read_capped_stream(FakeReadable(b"abc", b"de"), 10)
    assert data.decode() == "abcde"


async def test_read_capped_stream_stops_as_soon_as_cap_is_exceeded() -> None:
    """dừng ngay khi vượt hạn mức thay vì buffer hết rồi mới kiểm"""
    big = b"A" * 4
    stream = FakeReadable(big, big, big)  # 12 byte, hạn 5
    with pytest.raises(RemoteDownloadError, match="vượt giới hạn"):
        await read_capped_stream(stream, 5)
    assert stream.destroyed is True, "stream phải bị huỷ, không tải nốt phần còn lại"


async def test_read_capped_stream_exactly_at_cap_is_accepted() -> None:
    """đúng bằng hạn mức thì vẫn nhận"""
    data = await read_capped_stream(FakeReadable(bytes(8)), 8)
    assert len(data) == 8


async def _outcome_within_2s(coro: Coroutine[Any, Any, object]) -> str:
    """Kết quả của một readCappedStream: "huy" nếu từ chối vì abort, "treo" nếu quá 2s không xong (sabotage bỏ
    abort -> treo, biến thành assert đỏ GỌN thay vì để test-runner timeout)."""
    task: asyncio.Task[object] = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({task}, timeout=2)
    if not done:
        task.cancel()
        return "treo"
    try:
        task.result()
    except RemoteDownloadError as exc:
        return "huy" if "hủy" in str(exc) else f"loi:{exc}"
    return "xong"


async def test_read_capped_stream_already_aborted_signal_with_endless_stream_rejects_at_once() -> None:
    """signal đã abort SẴN + stream vô tận thì từ chối NGAY, không kẹt đọc"""
    stream = NeverEndingReadable()
    signal = AbortSignal()
    signal.abort()
    assert await _outcome_within_2s(read_capped_stream(stream, 10, signal)) == "huy"


async def test_read_capped_stream_abort_midway_destroys_stream_and_rejects() -> None:
    """abort GIỮA CHỪNG thì huỷ stream và từ chối - đúng ca nguồn nhỏ giọt"""
    stream = NeverEndingReadable()
    signal = AbortSignal()
    pending = read_capped_stream(stream, 1_000_000, signal)
    asyncio.get_running_loop().call_later(0.01, signal.abort)
    assert await _outcome_within_2s(pending) == "huy", "abort phải làm từ chối trong 2s, không treo"
    assert stream.destroyed is True, "abort phải huỷ stream, không để socket sống tiếp"


# ------------------------------------------------------------------ decompressBody

_HTML = "<html><body>Giá vàng hôm nay tăng mạnh</body></html>"
_MAX = 1024 * 1024


def test_decompress_body_no_content_encoding_keeps_as_is() -> None:
    """không có content-encoding thì giữ nguyên"""
    data = _HTML.encode()
    assert decompress_body(data, None, _MAX).decode() == _HTML
    assert decompress_body(data, "identity", _MAX).decode() == _HTML


def test_decompress_body_gunzips_znews_tienphong_bug() -> None:
    """giải nén gzip (lỗi thật của znews.vn, tienphong.vn)"""
    gzipped = gzip.compress(_HTML.encode())
    # Không giải nén thì ra rác nhị phân - đây là bug cũ
    assert gzipped.decode("utf-8", errors="replace") != _HTML
    assert decompress_body(gzipped, "gzip", _MAX).decode() == _HTML


def test_decompress_body_deflate_both_with_header_and_raw() -> None:
    """giải nén deflate cả kiểu có header lẫn deflate thô"""
    assert decompress_body(zlib.compress(_HTML.encode()), "deflate", _MAX).decode() == _HTML
    raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw_deflate = raw.compress(_HTML.encode()) + raw.flush()
    assert decompress_body(raw_deflate, "deflate", _MAX).decode() == _HTML


def test_decompress_body_brotli() -> None:
    """giải nén brotli"""
    brotli = pytest.importorskip("brotli")
    if srd._load_brotli() is None:  # pyright: ignore[reportPrivateUsage]
        pytest.skip("brotli < 1.2 has no bounded decompressor; the port refuses br then")
    compressed = brotli.compress(_HTML.encode())
    assert decompress_body(compressed, "br", _MAX).decode() == _HTML


def test_decompress_body_header_uppercase_or_padded_still_accepted() -> None:
    """header viết hoa hoặc có khoảng trắng vẫn nhận"""
    gzipped = gzip.compress(_HTML.encode())
    assert decompress_body(gzipped, " GZIP ", _MAX).decode() == _HTML


def test_decompress_body_blocks_zip_bomb_when_output_exceeds_cap() -> None:
    """chặn zip bomb: bung ra vượt hạn mức thì ném lỗi"""
    bomb = gzip.compress(b"A" * (5 * 1024 * 1024))  # 5MB toàn 'A' nén rất nhỏ
    assert len(bomb) < 64 * 1024, "dữ liệu nén phải nhỏ, mới đúng tình huống bomb"
    with pytest.raises(RemoteDownloadError, match="Giải nén nội dung thất bại"):
        decompress_body(bomb, "gzip", 1024 * 1024)


def test_decompress_body_unknown_codec_reports_error_instead_of_garbage() -> None:
    """kiểu nén lạ thì báo lỗi thay vì trả rác"""
    with pytest.raises(RemoteDownloadError, match='Không giải nén được kiểu "zstd"'):
        decompress_body(_HTML.encode(), "zstd", _MAX)


def test_decompress_body_corrupt_data_does_not_crash_process() -> None:
    """dữ liệu hỏng không làm sập process"""
    with pytest.raises(RemoteDownloadError, match="Giải nén nội dung thất bại"):
        decompress_body(b"khong-phai-gzip", "gzip", _MAX)


# ------------------------------------------------------------------ downloadFromPublicUrl - chặn trước khi mở kết nối

_OPTS = DownloadOptions(max_bytes=1024)


def _forbidden_transport() -> httpx.MockTransport:
    """A transport that fails the test if anything reaches it: the block must happen BEFORE a connection."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"request must not be sent: {request.url.host}")

    return httpx.MockTransport(handler)


async def test_download_from_public_url_blocks_url_pointing_to_loopback() -> None:
    """chặn URL trỏ vào loopback (dashboard của chính bot)"""
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await download_from_public_url(
            "http://127.0.0.1:3900/api/threads", _OPTS, transport=_forbidden_transport()
        )


async def test_download_from_public_url_blocks_cloud_metadata_endpoint() -> None:
    """chặn endpoint metadata của cloud"""
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await download_from_public_url(
            "http://169.254.169.254/latest/meta-data/", _OPTS, transport=_forbidden_transport()
        )


async def test_download_from_public_url_blocks_internal_ip_and_ipv6_loopback_in_url() -> None:
    """chặn IP nội bộ và IPv6 loopback ghi thẳng trong URL"""
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await download_from_public_url("http://192.168.1.1/router", _OPTS, transport=_forbidden_transport())
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await download_from_public_url("http://[::1]:3900/", _OPTS, transport=_forbidden_transport())


async def test_download_from_public_url_only_accepts_http_https() -> None:
    """chỉ nhận http/https"""
    with pytest.raises(RemoteDownloadError, match=r"Chỉ hỗ trợ http/https"):
        await download_from_public_url("file:///C:/Windows/win.ini", _OPTS, transport=_forbidden_transport())
    with pytest.raises(RemoteDownloadError, match=r"Chỉ hỗ trợ http/https"):
        await download_from_public_url("ftp://vi-du.vn/tep.zip", _OPTS, transport=_forbidden_transport())


async def test_download_from_public_url_garbage_url_reports_clear_error() -> None:
    """URL rác trả lỗi rõ ràng"""
    with pytest.raises(RemoteDownloadError, match="URL không hợp lệ"):
        await download_from_public_url("khong-phai-url", _OPTS, transport=_forbidden_transport())


# ---- added: not in the TypeScript suite ----------------------------------------------------------------


class _RawBody(httpx.AsyncByteStream):
    """Streams the bytes untouched. ``httpx.Response(content=...)`` is read eagerly AND decoded by httpx, which
    would hide the compressed bytes this module must see (a real transport returns an unread stream)."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self) -> AsyncIterator[bytes]:
        half = len(self._data) // 2
        for part in (self._data[:half], self._data[half:]):
            if part:
                yield part


def _resp(status: int, content: bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
    all_headers = {"content-length": str(len(content)), **(headers or {})}
    return httpx.Response(status, headers=all_headers, stream=_RawBody(content))


def _mock(handler_responses: dict[str, httpx.Response]) -> httpx.MockTransport:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler_responses[str(request.url)]

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


async def test_download_from_public_url_returns_file_with_name_and_media_type() -> None:
    """tải thành công: byte, media type bỏ phần charset, tên file đã lọc ký tự"""
    transport = _mock(
        {
            "http://files.example.test/a/bao%20gia%20%C4%91%E1%BA%B9p.pdf?x=1": _resp(
                200, content=b"%PDF-demo", headers={"content-type": "application/pdf; charset=binary"}
            )
        }
    )
    file = await download_from_public_url(
        "http://files.example.test/a/bao%20gia%20%C4%91%E1%BA%B9p.pdf?x=1", _OPTS, transport=transport
    )
    assert file.data == b"%PDF-demo"
    assert file.media_type == "application/pdf"
    assert file.file_name == "bao_gia___p.pdf"


async def test_download_from_public_url_decompresses_before_returning() -> None:
    """giải nén TRƯỚC khi trả về: caller nào cũng đang coi đây là dữ liệu thô"""
    body = gzip.compress(_HTML.encode())
    transport = _mock(
        {
            "https://news.example.test/": _resp(
                200, content=body, headers={"content-encoding": "gzip", "content-type": "text/html"}
            )
        }
    )
    file = await download_from_public_url(
        "https://news.example.test/", DownloadOptions(max_bytes=_MAX), transport=transport
    )
    assert file.data.decode() == _HTML
    assert file.file_name == "tep-tai-ve"


async def test_download_from_public_url_follows_redirect_and_rechecks_every_hop() -> None:
    """tự đi theo redirect nhưng mỗi hop đều bị kiểm lại"""
    transport = _mock(
        {
            "http://a.example.test/start": _resp(302, headers={"location": "/next"}),
            "http://a.example.test/next": _resp(200, content=b"ok"),
        }
    )
    file = await download_from_public_url("http://a.example.test/start", _OPTS, transport=transport)
    assert file.data == b"ok"

    evil = _mock(
        {
            "http://a.example.test/start": _resp(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            ),
        }
    )
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await download_from_public_url("http://a.example.test/start", _OPTS, transport=evil)
    assert evil.seen == ["http://a.example.test/start"]  # type: ignore[attr-defined]


async def test_download_from_public_url_redirect_to_non_http_scheme_is_refused() -> None:
    """redirect sang file:// bị chặn như URL đầu vào"""
    transport = _mock({"http://a.example.test/x": _resp(301, headers={"location": "file:///etc/passwd"})})
    with pytest.raises(RemoteDownloadError, match=r"Chỉ hỗ trợ http/https"):
        await download_from_public_url("http://a.example.test/x", _OPTS, transport=transport)


async def test_download_from_public_url_too_many_redirects() -> None:
    """quá MAX_REDIRECTS lần chuyển hướng thì dừng"""
    transport = _mock({"http://a.example.test/loop": _resp(302, headers={"location": "/loop"})})
    with pytest.raises(RemoteDownloadError, match="Quá 3 lần chuyển hướng"):
        await download_from_public_url("http://a.example.test/loop", _OPTS, transport=transport)
    assert len(transport.seen) == srd.MAX_REDIRECTS + 1  # type: ignore[attr-defined]


async def test_download_from_public_url_http_error_status() -> None:
    """HTTP không phải 2xx thì báo mã"""
    transport = _mock({"http://a.example.test/": _resp(404, content=b"no")})
    with pytest.raises(RemoteDownloadError, match="HTTP 404"):
        await download_from_public_url("http://a.example.test/", _OPTS, transport=transport)


async def test_download_from_public_url_declared_length_over_cap_is_refused_before_reading() -> None:
    """có Content-Length thì chặn trước khi đọc byte nào"""
    transport = _mock(
        {"http://a.example.test/": _resp(200, content=b"x" * 10, headers={"content-length": "5000"})}
    )
    with pytest.raises(RemoteDownloadError, match="vượt giới hạn"):
        await download_from_public_url("http://a.example.test/", _OPTS, transport=transport)


async def test_download_from_public_url_body_over_cap_without_length_is_cut() -> None:
    """không có Content-Length mà vượt hạn mức vẫn bị cắt khi đọc"""

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for _ in range(10):
                yield b"x" * 400

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, stream=Body()))
    with pytest.raises(RemoteDownloadError, match="vượt giới hạn"):
        await download_from_public_url("http://a.example.test/", _OPTS, transport=transport)


async def test_download_from_public_url_empty_body_is_an_error() -> None:
    """nội dung rỗng thì báo lỗi"""
    transport = _mock({"http://a.example.test/": _resp(200, content=b"")})
    with pytest.raises(RemoteDownloadError, match="Nội dung rỗng"):
        await download_from_public_url("http://a.example.test/", _OPTS, transport=transport)


async def test_download_from_public_url_unsupported_encoding_does_not_return_garbage() -> None:
    """kiểu nén lạ ở server thì báo lỗi, không trả rác vào context"""
    transport = _mock(
        {"http://a.example.test/": _resp(200, content=b"abc", headers={"content-encoding": "zstd"})}
    )
    with pytest.raises(RemoteDownloadError, match="Giải nén nội dung thất bại"):
        await download_from_public_url("http://a.example.test/", _OPTS, transport=transport)


async def test_download_from_public_url_timeout_is_reported_with_the_configured_wait() -> None:
    """hết thời gian chờ báo đúng số ms đã cấu hình"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(RemoteDownloadError, match="Hết thời gian chờ 250ms"):
        await download_from_public_url(
            "http://a.example.test/",
            DownloadOptions(max_bytes=10, timeout_ms=250),
            transport=httpx.MockTransport(handler),
        )


async def test_download_from_public_url_abort_cancels_a_hanging_handshake() -> None:
    """abort khi đang bắt tay kết nối thì dừng ngay với lỗi đã hủy"""
    never = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await never.wait()
        return _resp(200)

    signal = AbortSignal()
    asyncio.get_running_loop().call_later(0.01, signal.abort)
    with pytest.raises(RemoteDownloadError, match="Đã hủy tải"):
        await asyncio.wait_for(
            download_from_public_url(
                "http://a.example.test/",
                DownloadOptions(max_bytes=10, signal=signal),
                transport=httpx.MockTransport(handler),
            ),
            timeout=2,
        )


async def test_download_from_public_url_already_aborted_signal_sends_nothing() -> None:
    """signal đã abort sẵn thì không mở kết nối nào"""
    signal = AbortSignal()
    signal.abort()
    with pytest.raises(RemoteDownloadError, match="Đã hủy tải"):
        await download_from_public_url(
            "http://a.example.test/",
            DownloadOptions(max_bytes=10, signal=signal),
            transport=_forbidden_transport(),
        )


async def test_open_guarded_request_extra_headers_are_an_allow_list() -> None:
    """header thêm chỉ nhận range / Accept-Encoding, không cho ghi đè Host / Cookie / Authorization"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _resp(206, content=b"x")

    transport = httpx.MockTransport(handler)
    url = parse_public_url("http://a.example.test/v.mp4")
    res = await open_guarded_request(url, 1000, "GET", {"range": "bytes=0-0"}, transport=transport)
    await res.aclose()
    assert res.status_code == 206
    assert captured[0].headers["range"] == "bytes=0-0"
    assert captured[0].headers["host"] == "a.example.test"
    assert "Mozilla/5.0" in captured[0].headers["user-agent"]

    with pytest.raises(ValueError, match="Header không được phép"):
        await open_guarded_request(
            url,
            1000,
            "GET",
            {"Host": "evil.example.test"},  # type: ignore[typeddict-unknown-key]
            transport=transport,
        )


def test_parse_public_url_accepts_scheme_urls_and_rejects_the_rest() -> None:
    """URL không scheme / thiếu host là không hợp lệ; file:// vẫn parse được (bị chặn ở bước sau)"""
    assert parse_public_url("https://example.test/a").host == "example.test"
    assert parse_public_url("file:///C:/Windows/win.ini").scheme == "file"
    for raw in ["", "khong-phai-url", "http://", "//example.test/x"]:
        with pytest.raises(RemoteDownloadError, match="URL không hợp lệ"):
            parse_public_url(raw)


# ---- added: the pinned connection (what guardedLookup did) ------------------------------------------------

_OK_RESPONSE = b"HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\ncontent-length: 5\r\n\r\nhello"


class RecordingBackend(httpcore.AsyncMockBackend):
    """In-memory network backend that records which IP the socket was opened to."""

    def __init__(self, buffer: list[bytes]) -> None:
        super().__init__(buffer)
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - signature fixed by httpcore
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected.append((host, port))
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


class CountingResolver:
    def __init__(self, *answers: list[str]) -> None:
        self._answers = list(answers)
        self.calls: list[str] = []

    async def __call__(self, hostname: str) -> list[str]:
        self.calls.append(hostname)
        return self._answers[min(len(self.calls), len(self._answers)) - 1]


async def test_guarded_transport_connects_to_the_vetted_ip_resolving_only_once() -> None:
    """chặn DNS rebinding: kết nối tới đúng IP đã kiểm, chỉ phân giải một lần"""
    # The second answer would be the rebinding swap to an internal address; it must never be asked for.
    resolver = CountingResolver(["93.184.216.34"], ["127.0.0.1"])
    backend = RecordingBackend([_OK_RESPONSE])
    transport = GuardedTransport(resolver=resolver, network_backend=backend)
    try:
        file = await download_from_public_url(
            "http://files.example.test:8080/a.txt", _OPTS, transport=transport
        )
    finally:
        await transport.aclose()
    assert file.data == b"hello"
    assert resolver.calls == ["files.example.test"]
    assert backend.connected == [("93.184.216.34", 8080)]


@pytest.mark.parametrize(
    "answer",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.0.0.7"],
        ["::1"],
        ["::ffff:127.0.0.1"],
        ["93.184.216.34", "192.168.0.10"],  # ONE bad address among good ones blocks the whole host
    ],
)
async def test_guarded_transport_refuses_host_resolving_to_non_public_address(answer: list[str]) -> None:
    """hostname phân giải ra IP nội bộ (kể cả lẫn với IP public) thì bị chặn, không mở socket nào"""
    backend = RecordingBackend([_OK_RESPONSE])
    transport = GuardedTransport(resolver=CountingResolver(answer), network_backend=backend)
    try:
        with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
            await download_from_public_url("http://evil.example.test/x", _OPTS, transport=transport)
    finally:
        await transport.aclose()
    assert backend.connected == []


async def test_guarded_transport_refuses_host_that_does_not_resolve() -> None:
    """không phân giải được hostname thì báo lỗi rõ"""
    backend = RecordingBackend([_OK_RESPONSE])
    transport = GuardedTransport(resolver=CountingResolver([]), network_backend=backend)
    try:
        with pytest.raises(RemoteDownloadError, match="Không phân giải được"):
            await download_from_public_url("http://gone.example.test/x", _OPTS, transport=transport)
    finally:
        await transport.aclose()
    assert backend.connected == []


async def test_guarded_transport_resolver_failure_is_reported_as_unresolvable() -> None:
    """lỗi DNS (gaierror) thành thông báo 'Không phân giải được', không lộ exception hệ thống"""

    async def failing(hostname: str) -> list[str]:
        raise OSError(11001, "getaddrinfo failed")

    backend = RecordingBackend([_OK_RESPONSE])
    transport = GuardedTransport(resolver=failing, network_backend=backend)
    try:
        with pytest.raises(RemoteDownloadError, match="Không phân giải được"):
            await download_from_public_url("http://gone.example.test/x", _OPTS, transport=transport)
    finally:
        await transport.aclose()
    assert backend.connected == []


async def test_guarded_transport_rechecks_each_redirect_hop_through_the_resolver() -> None:
    """mỗi hop redirect được phân giải và kiểm lại: hop 2 trỏ vào IP nội bộ thì bị chặn"""
    redirect = (
        b"HTTP/1.1 302 Found\r\nlocation: http://internal.example.test/secret\r\ncontent-length: 0\r\n\r\n"
    )
    resolver_answers = {"start.example.test": ["93.184.216.34"], "internal.example.test": ["10.1.2.3"]}

    async def resolver(hostname: str) -> list[str]:
        return resolver_answers[hostname]

    backend = RecordingBackend([redirect])
    transport = GuardedTransport(resolver=resolver, network_backend=backend)
    try:
        with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
            await download_from_public_url("http://start.example.test/go", _OPTS, transport=transport)
    finally:
        await transport.aclose()
    assert backend.connected == [("93.184.216.34", 80)]


async def test_guarded_transport_literal_ip_host_is_vetted_without_dns() -> None:
    """URL ghi thẳng IP thì không hỏi DNS mà vẫn bị kiểm trong network backend"""
    resolver = CountingResolver(["8.8.8.8"])
    backend = RecordingBackend([_OK_RESPONSE])
    backend_guard = srd.GuardedNetworkBackend(resolver=resolver, inner=backend)
    with pytest.raises(RemoteDownloadError, match="Chặn địa chỉ nội bộ"):
        await backend_guard.connect_tcp("172.16.0.9", 80)
    stream = await backend_guard.connect_tcp("8.8.8.8", 80)
    await stream.aclose()
    assert resolver.calls == []
    assert backend.connected == [("8.8.8.8", 80)]


@pytest.mark.skipif(importlib.util.find_spec("brotli") is not None, reason="brotli is installed")
def test_decompress_body_brotli_without_library_is_refused_not_decoded_unbounded() -> None:
    """thiếu thư viện brotli thì từ chối thay vì giải nén không giới hạn"""
    with pytest.raises(RemoteDownloadError, match="Giải nén nội dung thất bại"):
        decompress_body(b"\x0b\x00\x80abc\x03", "br", _MAX)


def test_decompress_body_brotli_unavailable_is_not_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    """không giải nén được br an toàn thì không khai br trong Accept-Encoding"""
    monkeypatch.setattr(srd, "_load_brotli", lambda: None)
    assert srd._browser_headers()["accept-encoding"] == "gzip, deflate"  # pyright: ignore[reportPrivateUsage]
