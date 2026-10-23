"""The fetch guard: addresses it accepts, redirects, size and time limits. The network is replaced by a mock
transport and the DNS by a table, so nothing here leaves the machine."""

from __future__ import annotations

import asyncio
import gzip
from collections.abc import Callable, Iterable, Mapping

import httpcore
import httpx
import pytest

from agentcore.harness.tools.builtin.netguard import (
    BlockedAddressError,
    FetchError,
    _PinnedBackend,  # pyright: ignore[reportPrivateUsage]
    fetch,
    is_public,
    public_address,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _dns(table: Mapping[str, list[str]]) -> Callable[[str, int], asyncio.Future[list[str]]]:
    async def resolve(host: str, port: int) -> list[str]:
        return table[host]

    return resolve  # type: ignore[return-value]


def _mock(handler: Handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("93.184.216.34", True),
        ("2606:4700:4700::1111", True),
        ("::ffff:8.8.8.8", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.18.0.4", False),
        ("192.168.0.9", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),  # noqa: S104 - an address under test, not a bind
        ("::1", False),
        ("fe80::1", False),
        ("fd12::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:10.0.0.1", False),
        ("not an address", False),
    ],
)
def test_only_a_globally_routable_address_is_public(address: str, public: bool) -> None:
    assert is_public(address) is public


async def test_a_name_with_private_and_public_answers_is_only_given_its_public_one() -> None:
    resolver = _dns({"mixed.example": ["10.0.0.7", "93.184.216.34"], "inside.example": ["10.0.0.7"]})

    assert await public_address("mixed.example", 443, resolver) == "93.184.216.34"
    with pytest.raises(BlockedAddressError):
        await public_address("inside.example", 443, resolver)


async def test_an_address_in_the_url_is_judged_without_asking_the_dns() -> None:
    async def never(host: str, port: int) -> list[str]:
        raise AssertionError("the DNS must not be asked for an address")

    assert await public_address("8.8.8.8", 80, never) == "8.8.8.8"
    with pytest.raises(BlockedAddressError):
        await public_address("::1", 80, never)


async def test_a_page_is_read_with_its_type_and_final_address() -> None:
    page = await fetch(
        "https://site.example/a",
        resolver=_dns({"site.example": ["93.184.216.34"]}),
        transport=_mock(lambda r: httpx.Response(200, text="hello", headers={"content-type": "text/html"})),
    )

    assert (page.status, page.content_type, page.data, page.truncated) == (200, "text/html", b"hello", False)
    assert page.url == "https://site.example/a"


async def test_requests_are_get_only_with_no_cookie_or_proxy_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    await fetch(
        "http://site.example/", resolver=_dns({"site.example": ["93.184.216.34"]}), transport=_mock(handler)
    )

    assert [r.method for r in seen] == ["GET"]
    assert "cookie" not in seen[0].headers
    assert "authorization" not in seen[0].headers


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://site.example/x", "gopher://site.example/", "site.example/x", "http://"],
)
async def test_only_http_and_https_are_fetched(url: str) -> None:
    with pytest.raises(FetchError) as refused:
        await fetch(url, resolver=_dns({}), transport=_mock(lambda r: httpx.Response(200)))

    assert refused.value.kind == "scheme"


async def test_a_form_is_posted_to_the_first_address_and_a_redirect_after_it_is_a_get() -> None:
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        if request.method == "POST":
            return httpx.Response(303, headers={"location": "/results"})
        return httpx.Response(200, text="found")

    page = await fetch(
        "https://search.example/html/",
        form={"q": "giá vàng"},
        resolver=_dns({"search.example": ["93.184.216.34"]}),
        transport=_mock(handler),
    )

    assert page.data == b"found"
    assert [(m, p) for m, p, _ in seen] == [("POST", "/html/"), ("GET", "/results")]
    assert seen[0][2] == b"q=gi%C3%A1+v%C3%A0ng"
    assert seen[1][2] == b""


async def test_a_redirect_is_followed_and_checked_from_the_start() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://other.example/new"})
        return httpx.Response(200, text="moved")

    page = await fetch(
        "https://site.example/old",
        resolver=_dns({"site.example": ["93.184.216.34"], "other.example": ["8.8.4.4"]}),
        transport=_mock(handler),
    )

    assert (page.data, page.url) == (b"moved", "https://other.example/new")


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1/",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://inside.example/",
    ],
)
async def test_a_redirect_into_a_private_address_is_refused(target: str) -> None:
    resolver = _dns({"site.example": ["93.184.216.34"], "inside.example": ["172.18.0.3"]})

    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://site.example/",
            resolver=resolver,
            transport=_mock(lambda r: httpx.Response(302, headers={"location": target})),
        )

    assert refused.value.kind == "blocked"


async def test_a_redirect_to_another_scheme_is_refused() -> None:
    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://site.example/",
            resolver=_dns({"site.example": ["93.184.216.34"]}),
            transport=_mock(lambda r: httpx.Response(302, headers={"location": "file:///etc/passwd"})),
        )

    assert refused.value.kind == "scheme"


async def test_a_loop_of_redirects_stops_after_the_limit() -> None:
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(request.url.path)
        return httpx.Response(302, headers={"location": f"/{len(hops)}"})

    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://site.example/",
            resolver=_dns({"site.example": ["93.184.216.34"]}),
            transport=_mock(handler),
            max_redirects=3,
        )

    assert refused.value.kind == "redirects"
    assert len(hops) == 4  # the first address and three redirects


async def test_a_body_over_the_limit_is_cut_and_says_so() -> None:
    page = await fetch(
        "https://site.example/",
        max_bytes=1000,
        resolver=_dns({"site.example": ["93.184.216.34"]}),
        transport=_mock(lambda r: httpx.Response(200, content=b"x" * 5000)),
    )

    assert (len(page.data), page.truncated) == (1000, True)


async def test_a_body_of_exactly_the_limit_is_not_cut() -> None:
    page = await fetch(
        "https://site.example/",
        max_bytes=1000,
        resolver=_dns({"site.example": ["93.184.216.34"]}),
        transport=_mock(lambda r: httpx.Response(200, content=b"x" * 1000)),
    )

    assert (len(page.data), page.truncated) == (1000, False)


@pytest.mark.parametrize("encoding", ["gzip", "br"])
async def test_a_compressed_body_is_refused_unread(encoding: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        bomb = gzip.compress(b"a" * 5_000_000)  # the bytes are never unpacked, whatever the header says
        return httpx.Response(200, content=bomb, headers={"content-encoding": encoding})

    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://site.example/",
            resolver=_dns({"site.example": ["93.184.216.34"]}),
            transport=_mock(handler),
        )

    assert refused.value.kind == "network"
    assert seen[0].headers["accept-encoding"] == "identity"


async def test_a_slow_site_is_given_up_on_at_the_deadline() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://site.example/",
            timeout_s=0.05,
            resolver=_dns({"site.example": ["93.184.216.34"]}),
            transport=_mock(slow),  # type: ignore[arg-type]
        )

    assert refused.value.kind == "timeout"


async def test_a_name_that_does_not_resolve_is_a_blocked_fetch_not_a_crash() -> None:
    async def nothing(host: str, port: int) -> list[str]:
        return []

    with pytest.raises(FetchError) as refused:
        await fetch(
            "https://nowhere.example/", resolver=nothing, transport=_mock(lambda r: httpx.Response(200))
        )

    assert refused.value.kind == "blocked"


class _Recorder(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's signature
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected.append((host, port))
        raise ConnectionRefusedError

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's signature
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def test_a_connection_goes_to_the_checked_address_and_to_nothing_else() -> None:
    recorder = _Recorder()
    backend = _PinnedBackend(recorder)
    backend.pins["site.example"] = "93.184.216.34"

    with pytest.raises(ConnectionRefusedError):
        await backend.connect_tcp("site.example", 443)
    with pytest.raises(BlockedAddressError):
        await backend.connect_tcp("unchecked.example", 443)
    with pytest.raises(BlockedAddressError):
        await backend.connect_unix_socket("/var/run/docker.sock")

    assert recorder.connected == [("93.184.216.34", 443)]


async def test_a_name_the_system_cannot_resolve_is_a_refused_fetch_not_a_crash() -> None:
    with pytest.raises(FetchError) as refused:
        await fetch("http://no-such-host.invalid/", transport=_mock(lambda r: httpx.Response(200)))

    assert refused.value.kind == "blocked"
