# ported from: src/video/whitelist-nguon-video.ts
"""Only allow downloading video from the hosts listed here.

WHY IT MUST EXIST: the bot reads messages from STRANGERS, and this tool takes a URL and goes to download it.
Without a gate here an outsider writing one message makes the VPS send a request anywhere, including
``http://127.0.0.1:*`` (other apps on the same machine) or the cloud provider's metadata endpoint. That is
SSRF, and it is far more dangerous than the worry "a video installs malware": a video file on disk that
nobody decodes is harmless, while SSRF reaches OTHER things.

An ALLOW-LIST, not a deny-list: a deny-list is always missing something, and what is missing is what gets in.

Forced deviation: the original relies on the WHATWG ``new URL()`` of Node, and the whole file reasons about
what THAT parser does (the ``\\`` host confusion, ``URL.href`` normalisation, ``searchParams``). Python's
``urllib.parse`` is NOT WHATWG (it keeps ``\\`` in the host), so using it would reopen the very hole the
original comments describe. ``phan_tich_url_whatwg`` below is therefore a small WHATWG-style parser for
``http``/``https`` (and just enough of other schemes to tell them apart): special-scheme slash handling,
last-``@`` userinfo split, host lower-casing, default-port removal, path/query percent-encoding and dot
segment removal. It deliberately does not implement IPv4 number-shorthand normalisation: any host that is
not in the allow-list is rejected either way, so the difference cannot change a verdict. ``u.href`` is
rebuilt WITHOUT userinfo because a URL with userinfo is rejected before ``href`` is read.
``URLSearchParams`` iteration is ``urllib.parse.parse_qsl`` (same ``+``/percent decoding), and JS
``decodeURIComponent`` is a strict ``unquote``.
"""

from __future__ import annotations

import contextlib
import ipaddress
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl, quote, unquote

NenTangVideo = Literal["tiktok", "facebook", "instagram"]
"""Platform recognised: decides which source to take at the layer above."""


@dataclass(frozen=True)
class _HostChoPhep:
    hau: str
    nen_tang: NenTangVideo


HOST_CHO_PHEP: list[_HostChoPhep] = [
    _HostChoPhep("tiktok.com", "tiktok"),
    _HostChoPhep("douyin.com", "tiktok"),
    _HostChoPhep("facebook.com", "facebook"),
    _HostChoPhep("fb.watch", "facebook"),
    _HostChoPhep("fb.com", "facebook"),
    # Instagram: reel/post/tv. The app's "Copy link" gives ``instagram.com/reel/<code>/?igsh=...``: matching
    # by SUFFIX covers ``www.`` and ``m.instagram.com`` too. Do NOT add ``threads.net/com``: yt-dlp has no
    # extractor for Threads (measured 2026-08, even force-generic gives ``Unsupported URL``).
    _HostChoPhep("instagram.com", "instagram"),
]
"""Allowed hosts with their platform.

Matched by host SUFFIX (``a.b.com`` matches ``b.com``), not ``includes``: ``includes`` lets
``tiktok.com.ke-tan-cong.net`` through. A regex over the whole URL is not used either:
``https://ke-tan-cong.net/?x=tiktok.com`` gets through."""

HOST_CHI_DE_CHUYEN_HUONG: list[str] = [
    "l.facebook.com",
    "lm.facebook.com",
    "l.instagram.com",
    "l.messenger.com",
]
"""Hosts that exist ONLY to REDIRECT, forbidden whatever the query carries.

This rule LOOKS redundant after ``mang_url_khac_trong_query``, and I nearly dropped it. The SUPERSET check
caught it: ``https://L.FaceBook.CoM/l.php?u=x`` was blocked by the old version while the "stronger" one LET
IT THROUGH, because ``x`` is not a URL so the shape rule sees nothing. The two rules catch two different
things: keep both.

(This is the lesson recorded in CLAUDE.md: replacing a security rule with a "stronger" one means proving the
new caught-set COVERS the old one, not only measuring the new direction. This time exactly that measurement
caught the regression.)

``l.instagram.com`` IS NOW A REAL SAFETY NET and must NOT be deleted: since ``instagram.com`` was added to the
allow-list, ``l.instagram.com`` MATCHES the suffix ``.instagram.com`` so it is blocked ONLY because this rule
runs BEFORE the allow-list. Remove it and ``https://l.instagram.com/?u=<payload that is not a URL>`` passes
the allow-list as a valid instagram host and goes straight down to yt-dlp: exactly the hole
``mang_url_khac_trong_query`` does NOT plug (it only sees a URL in the query, not ``u=x``).
``l.instagram.com`` is Instagram's REAL redirect-out gate (302). A test locks it.

``l.messenger.com`` is still redundant (messenger.com is not in the allow-list): kept as a record of intent
in case it is added later."""

# --------------------------------------------------------------------------- WHATWG-style URL parsing

_C0_VA_DAU_CACH = "".join(chr(i) for i in range(0x21))
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
_HOST_CAM = frozenset("\x00\t\n\r #/:<>?@[\\]^|%")
_PORT_MAC_DINH = {"http": 80, "https": 443}


@dataclass(frozen=True)
class UrlPhanTich:
    """What the original reads from a ``URL``: ``protocol`` (with the colon), ``username``, ``password``,
    ``hostname`` (lower-case, IPv6 keeps its brackets), ``href`` and the raw ``search`` (query without
    ``?``)."""

    protocol: str
    username: str = ""
    password: str = ""
    hostname: str = ""
    href: str = ""
    query: str = ""


def _ma_hoa(text: str, cam: str) -> str:
    out: list[str] = []
    for ch in text:
        if ord(ch) <= 0x20 or ord(ch) >= 0x7F or ch in cam:
            out.append(quote(ch, safe=""))
        else:
            out.append(ch)
    return "".join(out)


def _bo_dau_cham(path: str) -> str:
    """Remove ``.`` and ``..`` segments (also their ``%2e`` forms), as the WHATWG path state does."""
    segs = path.split("/")[1:]
    out: list[str] = []
    for i, seg in enumerate(segs):
        low = seg.lower()
        la_cuoi = i == len(segs) - 1
        if low in ("..", ".%2e", "%2e.", "%2e%2e"):
            if out:
                out.pop()
            if la_cuoi:
                out.append("")
        elif low in (".", "%2e"):
            if la_cuoi:
                out.append("")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def _phan_tich_host(host_tho: str) -> str | None:
    if host_tho.startswith("["):
        if not host_tho.endswith("]"):
            return None
        try:
            ipaddress.IPv6Address(host_tho[1:-1])
        except ValueError:
            return None
        return host_tho.lower()
    try:
        host = unquote(host_tho, errors="strict")
    except UnicodeDecodeError:
        return None
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    host = host.lower()
    if host == "" or any(ch in _HOST_CAM or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in host):
        return None
    return host


def phan_tich_url_whatwg(chuoi: str) -> UrlPhanTich | None:
    """``new URL(chuoi)``: ``None`` where it would THROW. See the module docstring for what is covered."""
    s = chuoi.strip(_C0_VA_DAU_CACH)
    s = re.sub(r"[\t\n\r]", "", s)
    m = _SCHEME.match(s)
    if m is None:
        return None
    scheme = m.group(1).lower()
    if scheme not in _PORT_MAC_DINH:
        # Another scheme (file:, ftp:, javascript: ...): the caller only needs the protocol to reject it.
        return UrlPhanTich(protocol=f"{scheme}:")
    rest = s[m.end() :].lstrip("/\\")  # special scheme: any number of slashes before the authority
    cuoi = next((i for i, ch in enumerate(rest) if ch in "/\\?#"), len(rest))
    authority, sau = rest[:cuoi], rest[cuoi:]

    username = password = ""
    host_port = authority
    if "@" in authority:
        i = authority.rfind("@")
        userinfo, host_port = authority[:i], authority[i + 1 :]
        username, _, password = userinfo.partition(":")

    if host_port.startswith("["):
        dong = host_port.find("]")
        if dong < 0:
            return None
        host_tho, phan_con = host_port[: dong + 1], host_port[dong + 1 :]
        if phan_con != "" and not phan_con.startswith(":"):
            return None
        port_tho = phan_con[1:]
    else:
        host_tho, _, port_tho = host_port.partition(":")
    hostname = _phan_tich_host(host_tho)
    if hostname is None:
        return None

    port_text = ""
    if port_tho != "":
        if not re.fullmatch(r"[0-9]+", port_tho) or int(port_tho) > 65535:
            return None
        if int(port_tho) != _PORT_MAC_DINH[scheme]:
            port_text = f":{int(port_tho)}"

    phan_manh = ""
    co_manh = False
    if "#" in sau:
        sau, _, phan_manh = sau.partition("#")
        co_manh = True
    query = ""
    co_query = False
    if "?" in sau:
        sau, _, query = sau.partition("?")
        co_query = True
    path = sau.replace("\\", "/") or "/"
    path = _bo_dau_cham(_ma_hoa(path, '"#<>?`{}'))
    query = _ma_hoa(query, "\"#<>'")
    phan_manh = _ma_hoa(phan_manh, '"<>`')

    href = f"{scheme}://{hostname}{port_text}{path}"
    if co_query:
        href += f"?{query}"
    if co_manh:
        href += f"#{phan_manh}"
    return UrlPhanTich(
        protocol=f"{scheme}:", username=username, password=password, hostname=hostname, href=href, query=query
    )


# --------------------------------------------------------------------------- the rules


def mang_url_khac_trong_query(query: str) -> bool:
    """Does this URL CARRY ANOTHER URL inside a query parameter?

    This is the SSRF layer, and it replaces a WRONG-WAY patch of the previous round.

    The previous version forbade by DOMAIN NAME: ``l.facebook.com``, ``lm.facebook.com``. But the redirect
    capability is NOT in those two names: ``/l.php?u=`` and ``/flx/warn/?u=`` work just the same on
    ``www.facebook.com``, ``m.facebook.com``, ``mbasic.facebook.com``, ``free.facebook.com``, the names that
    MUST be let through because the real videos live there. Forbidding by domain is locking one door of a
    ten-door building.

    MEASURED with a real listener at ``127.0.0.1:8791``: all 5 variants above passed the whitelist AND made
    yt-dlp send a real request to the internal address. If the listener returned ``content-type: video/mp4``
    yt-dlp even returned a ``videoUrl`` pointing at ``127.0.0.1`` itself, and that address then flowed down to
    the send path.

    The rule here is about SHAPE, not names: reject every URL carrying another address in its query. So it
    also covers redirect endpoints nobody knows yet, instead of chasing names one by one.

    ACCURACY MEASURED: blocks 8/8 attack payloads (including ``//host`` without a scheme and the
    double-encoded ``%2568ttp``), wrongly blocks 0/10 real link shapes (tried with ``fbclid``, ``mibextid``,
    ``is_from_webapp``, ``sender_device``). A real video link never puts another URL in its query.

    ``query`` is the raw query string of the parsed URL (``u.searchParams``).
    """
    for _, gia_tri in parse_qsl(query, keep_blank_values=True):
        # ``searchParams`` already decoded one layer. Decode ONE MORE to catch the double-encoded form
        # (``%2568ttp`` -> ``%68ttp`` -> ``http``), the most obvious way around once you know a filter exists.
        v = gia_tri.strip()
        # A broken encoding keeps the one-layer-decoded text: it can still be checked.
        with contextlib.suppress(UnicodeDecodeError):
            v = unquote(v, errors="strict").strip()
        # An explicit scheme (``http://``, ``https://``) OR the scheme-less form (``//host``).
        if re.match(r"^(https?:)?//", v, re.IGNORECASE):
            return True
        # Still-percent form after decoding: ``https%3a//...``
        if re.match(r"^https?%3a", v, re.IGNORECASE):
            return True
    return False


@dataclass(frozen=True)
class KetQuaWhitelistOk:
    nen_tang: NenTangVideo
    url: str
    """The NORMALISED URL (``URL.href``), NOT the string the user sent.

    This is where a REAL vulnerability once existed, proven to run, so read carefully before changing: this
    function checks the host with the WHATWG parser, while yt-dlp re-parses with Python's ``urllib``. The two
    do not agree about ``\\``:

        payload: http://tiktok.com\\@127.0.0.1:8791/api/tuning
        WHATWG -> hostname "tiktok.com"      (whitelist LETS IT THROUGH)
        Python -> hostname "127.0.0.1" :8791 (yt-dlp CALLS HERE)

    A server was set up at 127.0.0.1:8791 and the real yt-dlp run: the internal server RECEIVED the request.
    So the whitelist guarded one address while yt-dlp went to another: exactly what this layer exists to
    block.

    ``href`` normalises ``\\`` to ``/`` so Python re-reads ``tiktok.com``. Returning the raw string reopens
    the hole."""
    ok: Literal[True] = True


@dataclass(frozen=True)
class KetQuaWhitelistLoi:
    loi: str
    ok: Literal[False] = False


KetQuaWhitelist = KetQuaWhitelistOk | KetQuaWhitelistLoi


def kiem_nguon_video(url_tho: str) -> KetQuaWhitelist:
    """Is this URL allowed to download, and if so which platform does it belong to.

    Returns an object instead of raising: the caller is a tool, and the repo rule is that a tool does NOT
    raise into the agent loop.
    """
    chuoi = url_tho.strip()
    if chuoi == "":
        return KetQuaWhitelistLoi("Chưa có đường dẫn video.")

    u = phan_tich_url_whatwg(chuoi)
    if u is None:
        return KetQuaWhitelistLoi("Đường dẫn không hợp lệ - phải là một URL đầy đủ.")

    # ONLY http/https. Blocks ``file://`` (read a file on the machine), ``ftp://``, and odd schemes that a
    # download library may understand in a surprising way.
    if u.protocol not in ("https:", "http:"):
        return KetQuaWhitelistLoi("Chỉ nhận đường dẫn http hoặc https.")

    # Reject the userinfo part (``user:pass@host``). This is the COMMON layer of the whole family "the real
    # host sits after the @": different parsers cut the userinfo at different places, so a URL valid for one
    # side points elsewhere for the other. A real TikTok/Facebook link never has userinfo, so blocking
    # outright loses nothing.
    if u.username != "" or u.password != "":
        return KetQuaWhitelistLoi("Đường dẫn chứa thông tin đăng nhập - không nhận.")

    host = u.hostname.lower().removesuffix(".")

    # The anti-redirect rule runs BEFORE the allow-list: see the comment of ``mang_url_khac_trong_query``.
    if host in HOST_CHI_DE_CHUYEN_HUONG or mang_url_khac_trong_query(u.query):
        return KetQuaWhitelistLoi(
            "Đường dẫn này mang một địa chỉ khác bên trong (dạng link chuyển tiếp), không phải link "
            "video. Xin người dùng gửi link video gốc."
        )

    khop = next((h for h in HOST_CHO_PHEP if host == h.hau or host.endswith(f".{h.hau}")), None)
    if khop is None:
        return KetQuaWhitelistLoi(
            "Chỉ tải được video từ TikTok, Facebook và Instagram. Đường dẫn này không thuộc ba nơi đó."
        )

    # ``u.href`` and NOT ``chuoi``: see the comment on ``KetQuaWhitelistOk.url``.
    return KetQuaWhitelistOk(nen_tang=khop.nen_tang, url=u.href)


def tim_url_trong_chu(chu: str) -> str | None:
    """Pull the first video URL found in a piece of text.

    People rarely paste only the link: they write "tải hộ cái này với https://vt.tiktok.com/ABC/ nhé". The
    model could extract it itself, but then it is a different way every time; extracting here means the
    whitelist rule always runs on the normalised string.
    """
    khop = re.search(r"https?://[^\s<>\"']+", chu, re.IGNORECASE)
    if khop is None:
        return None
    # Drop punctuation stuck to the tail when people write "... link https://a.b/c."
    return re.sub(r"[.,;:!?)\]}]+$", "", khop.group(0))
