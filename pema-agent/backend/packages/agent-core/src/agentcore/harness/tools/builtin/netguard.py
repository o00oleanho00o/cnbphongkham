"""Fetching a URL for a tool without letting the model, or a page it reads, reach the machine's own network.

The model decides which address to fetch and it reads text from strangers, so every address is untrusted: a
fetch must never land on this host, a private network (the other services of the stack), or a cloud metadata
address. What this module does about it:

- only http and https;
- the host is resolved here and only a public address is ever connected to; the connection goes to exactly the
  address that was checked (no second lookup that could answer differently), the name stays in the URL so TLS
  still checks the certificate;
- every redirect is checked again from the start, at most ``MAX_REDIRECTS`` of them;
- no proxy from the environment, no cookies sent, GET only;
- only an uncompressed body is accepted (httpx unpacks a whole chunk before the cut, so a few hundred bytes of
  brotli could become hundreds of MB); it is read as a stream and cut at ``max_bytes``;
- one hard deadline for the whole fetch.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin

import httpcore
import httpx

MAX_BYTES: Final = 3 * 1024 * 1024
MAX_REDIRECTS: Final = 3
TIMEOUT_S: Final = 15.0
MAX_CONNECTIONS: Final = 10
REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
SCHEMES: Final = ("http", "https")
DEFAULT_PORTS: Final = {"http": 80, "https": 443}
USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
ACCEPT: Final = "text/html,text/plain,application/json,application/xml;q=0.9,*/*;q=0.1"
ACCEPT_LANGUAGE: Final = "vi-VN,vi;q=0.9,en;q=0.8"

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


class BlockedAddressError(Exception):
    """The address is not one a tool may connect to."""


class FetchError(Exception):
    """``kind``: ``blocked``, ``scheme``, ``redirects``, ``timeout`` or ``network``."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Fetched:
    url: str
    """The address the body came from, after redirects."""
    status: int
    content_type: str
    data: bytes
    truncated: bool
    """There was more than ``max_bytes`` of it."""


async def system_resolver(host: str, port: int) -> list[str]:
    """The addresses of ``host``; none when the name does not resolve."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return [str(info[4][0]) for info in infos]


def is_public(address: str) -> bool:
    """A globally routable address; the IPv4 inside an IPv4-mapped IPv6 address is judged as IPv4."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


async def public_address(host: str, port: int, resolver: Resolver) -> str:
    """The first public address of ``host``; ``BlockedAddressError`` when it has none (the private ones are
    never returned, however the name answers)."""
    try:
        ipaddress.ip_address(host)
        candidates: Sequence[str] = [host]
    except ValueError:
        candidates = await resolver(host, port)
    for candidate in candidates:
        if is_public(candidate):
            return candidate
    raise BlockedAddressError(f"{host} does not lead to a public address")


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Connects a host name only to the address that was checked for it."""

    def __init__(self, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        self.pins: dict[str, str] = {}
        self._inner: httpcore.AsyncNetworkBackend = inner or httpcore.AnyIOBackend()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - the signature of httpcore's backend
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        address = self.pins.get(host)
        if address is None:
            raise BlockedAddressError(f"{host} was not checked")
        return await self._inner.connect_tcp(
            address, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's signature
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise BlockedAddressError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _pinned_transport(backend: _PinnedBackend) -> httpx.AsyncHTTPTransport:
    transport = httpx.AsyncHTTPTransport()
    # shortcut: httpx has no hook for the network backend, so the transport's own pool is swapped for one that
    # has it; upgrade if httpx gains the option.
    transport._pool = httpcore.AsyncConnectionPool(  # pyright: ignore[reportPrivateUsage]
        ssl_context=httpx.create_ssl_context(), max_connections=MAX_CONNECTIONS, network_backend=backend
    )
    return transport


def _checked_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL as err:
        raise FetchError("scheme", "not a valid URL") from err
    if url.scheme not in SCHEMES or not url.host:
        raise FetchError("scheme", "only http and https addresses can be fetched")
    return url


async def fetch(
    url: str,
    *,
    max_bytes: int = MAX_BYTES,
    timeout_s: float = TIMEOUT_S,
    max_redirects: int = MAX_REDIRECTS,
    resolver: Resolver = system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
    form: Mapping[str, str] | None = None,
) -> Fetched:
    """GET ``url``; with ``form`` the first request is a POST of that form instead (a search page that refuses
    GET), and any redirect after it is a GET. A given ``transport`` replaces the network (tests); the address
    checks stay."""
    backend = _PinnedBackend()
    client = httpx.AsyncClient(
        transport=transport or _pinned_transport(backend),
        follow_redirects=False,
        trust_env=False,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
            "Accept-Language": ACCEPT_LANGUAGE,
            "Accept-Encoding": "identity",
        },
        timeout=timeout_s,
    )
    try:
        async with asyncio.timeout(timeout_s):
            return await _follow(client, backend, url, max_bytes, max_redirects, resolver, form)
    except TimeoutError as err:
        raise FetchError("timeout", "the fetch took too long") from err
    except httpx.TimeoutException as err:
        raise FetchError("timeout", "the site did not answer in time") from err
    except BlockedAddressError as err:
        raise FetchError("blocked", str(err)) from err
    except httpx.HTTPError as err:
        raise FetchError("network", f"the request failed ({type(err).__name__})") from err
    finally:
        await client.aclose()


async def _follow(
    client: httpx.AsyncClient,
    backend: _PinnedBackend,
    start: str,
    max_bytes: int,
    max_redirects: int,
    resolver: Resolver,
    form: Mapping[str, str] | None,
) -> Fetched:
    current = start
    for hop in range(max_redirects + 1):
        url = _checked_url(current)
        port = url.port or DEFAULT_PORTS[url.scheme]
        backend.pins[url.host] = await public_address(url.host, port, resolver)
        post = form is not None and hop == 0
        request = client.build_request("POST" if post else "GET", url, data=form if post else None)
        response = await client.send(request, stream=True)
        try:
            location = response.headers.get("location")
            if response.status_code in REDIRECT_STATUSES and location:
                current = urljoin(str(response.url), location)
                continue
            encoding = response.headers.get("content-encoding", "").strip().lower()
            if encoding not in ("", "identity"):
                raise FetchError("network", f"the site sent a compressed body ({encoding})")
            data, truncated = await _read(response, max_bytes)
            content_type = response.headers.get("content-type", "")
            return Fetched(str(response.url), response.status_code, content_type, data, truncated)
        finally:
            await response.aclose()
    raise FetchError("redirects", f"more than {max_redirects} redirects")


async def _read(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        room = max_bytes - size
        if len(chunk) > room:
            chunks.append(chunk[:room])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False
