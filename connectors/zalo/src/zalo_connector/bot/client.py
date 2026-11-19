# ported from: src/zalo-bot/zalo-bot-api-client.ts
"""Zalo Bot API client, written straight on an HTTP client, NO third party SDK.

Why no SDK although a few exist: the whole API is 10 plain JSON methods, measured at about 150 lines. The
popular packages all carry a price that is not worth paying (native build dependencies, an image library, a
translation library, or an old fork of a Telegram client). Compare with the personal-account library: that one
deserves to be a dependency because it is a REVERSED protocol of tens of thousands of lines that keeps
changing with Zalo Web; a documented REST API of 10 methods is the opposite.

Forced deviations: ``fetch`` becomes ``httpx.AsyncClient``; the injectable ``fetchImpl`` becomes ``transport``
(an ``httpx.MockTransport`` in tests, so nothing goes out to the network). Added (not in the original):
``set_webhook`` for webhook mode (``POST /bot{token}/setWebhook`` with ``url`` and ``secret_token``,
documented at https://bot.zapps.me/docs/apis/setWebhook/).
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, cast

import httpx

from .types import KetQuaGuiTin, ZaloBotUpdate

GOC_API_MAC_DINH = "https://bot-api.zaloplatforms.com"

MA_LOI_HET_HAN_CHO = 408
"""Code Zalo answers when the wait EXPIRES with no message: the NORMAL outcome of long polling, not an
incident.

Measured on the real API: ``{"ok":false,"description":"Request timeout","error_code":408}`` with HTTP 200,
returned after exactly the seconds asked (5015 ms / 10029 ms / 30042 ms for timeouts of 5/10/30). Caught by
the NUMERIC code, not by the words "Request timeout": the words can change or be translated, the code cannot.
"""

_TOKEN_IN_PATH = re.compile(r"/bot\d+(?::|%3A|&#58;|&#x3a;)[A-Za-z0-9_%\-.]+", re.IGNORECASE)


class LoiZaloBotApi(Exception):  # noqa: N818 - the name of the original, kept for the ported tests
    def __init__(
        self, message: str, method: str, http_status: int | None = None, ma_loi: int | str | None = None
    ) -> None:
        super().__init__(message)
        self.method = method
        self.http_status = http_status
        self.ma_loi = ma_loi


def _first_text(*candidates: object) -> str:
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


class ZaloBotClient:
    def __init__(
        self,
        token: str,
        *,
        goc_api: str = GOC_API_MAC_DINH,
        timeout_ms: int = 15_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._goc_api = goc_api
        self._timeout_ms = timeout_ms
        self._http = httpx.AsyncClient(transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _che(self, chu: str) -> str:
        """Mask the token in EVERY string about to enter an error message.

        Not redundant: the token sits in the URL PATH (``/bot{token}/{method}``), and the "body is not JSON"
        branch pastes up to 200 characters of the body into the error. That body comes from an intermediary
        gateway, not from Zalo, and many gateways (Apache, WAF, CDN) echo the path in their error page.
        Reproduced: the token travelled from there into the ``warning`` of an account update (onto the
        dashboard) and into the log file at start-up."""
        thay = chu.replace(self._token, "<token>") if self._token else chu
        # Second layer by SHAPE: a gateway may return the path URL-encoded (``%3A`` for ``:``) or
        # HTML-escaped, and then the literal replacement above does not match and the token goes straight into
        # the message.
        theo_hinh_dang = _TOKEN_IN_PATH.sub("/bot<token>", thay)
        # ADDITIVE layer (it replaces none of the above; lesson "a breaking change only measures the NEW
        # direction"): mask the SECRET part after the colon on its own. It catches two cases the layer above
        # lets through: a gateway using hex entities for the colon, and one that echoes only HALF the secret
        # without the ``<id>:`` prefix.
        parts = self._token.split(":")
        bi_mat = parts[1] if len(parts) > 1 else ""
        return theo_hinh_dang.replace(bi_mat, "<token>") if len(bi_mat) > 8 else theo_hinh_dang

    async def _goi(self, method: str, body: object | None = None, han_rieng_ms: int | None = None) -> Any:
        # The token is in the URL PATH, not a header (Zalo copied the Telegram style). Consequence to
        # remember: every place that logs an error MUST log ``method`` and absolutely never the URL; the URL
        # holds the token.
        url = f"{self._goc_api}/bot{self._token}/{method}"

        try:
            res = await self._http.post(
                url,
                content=json.dumps(body if body is not None else {}),
                headers={"Content-Type": "application/json"},
                timeout=(han_rieng_ms or self._timeout_ms) / 1000,
            )
        except Exception as err:
            # Wrap so the message carries no URL: ``str(err)`` of the HTTP stack may paste the URL in. Only
            # the class name goes in. ``from None`` keeps the original (with the URL) out of tracebacks and
            # logs.
            raise LoiZaloBotApi(f"Không gọi được {method}: {type(err).__name__}", method) from None

        chu = res.text
        phong_bi: dict[str, Any] | None
        try:
            parsed = json.loads(chu)
            phong_bi = cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None
        except ValueError:
            phong_bi = None
        if phong_bi is None:
            # MASK FIRST, then CUT. Cutting first breaks all three masks because all three match the FULL
            # string: a 200 mark falling in the middle of the secret leaks the head of the secret whole
            # (measured 4-24 characters depending on the padding).
            raise LoiZaloBotApi(
                f"{method} trả về thân không phải JSON (HTTP {res.status_code}): {self._che(chu)[:200]}",
                method,
                res.status_code,
            )

        if not res.is_success or phong_bi.get("ok") is not True:
            # The shape of the failure branch is not fully documented, so read defensively across the three
            # fields seen in the documentation and in other SDKs. ``description`` COMES FIRST: measured on the
            # real API, that is the field Zalo uses.
            error = phong_bi.get("error")
            loi = (
                _first_text(phong_bi.get("description"), phong_bi.get("message"), error)
                or (
                    str(cast(dict[str, Any], error)["message"])
                    if isinstance(error, dict) and "message" in error
                    else ""
                )
                or f"HTTP {res.status_code}"
            )
            # Mask this branch too: Zalo does not echo the path today, but an intermediary may step in and
            # return a JSON body that carries the URL.
            raise LoiZaloBotApi(
                f"{method} thất bại: {self._che(loi)}", method, res.status_code, phong_bi.get("error_code")
            )

        return phong_bi.get("result")

    async def get_me(self) -> dict[str, Any]:
        """Check that the token is alive and read the bot info."""
        result = await self._goi("getMe")
        return cast(dict[str, Any], result) if isinstance(result, dict) else {}

    async def get_updates(self, timeout_giay: int = 30) -> ZaloBotUpdate | None:
        """Long polling. There is NO ``offset`` parameter like Telegram (checked in the official docs): the
        server takes a message off the queue itself and reading it LOSES it. A process that dies after
        receiving and before finishing cannot get the message back; the caller must write it to the DB AT ONCE
        (``record_incoming_message``).

        Returns ONE update per call (or ``None`` when the wait expired with no message)."""
        # Add a margin so the client timeout does not cut BEFORE the server answers the expiry: cutting early
        # turns every poll round into a network error.
        han_ms = timeout_giay * 1000 + 7_000
        try:
            kq = await self._goi("getUpdates", {"timeout": timeout_giay}, han_ms)
        except LoiZaloBotApi as err:
            # WAIT EXPIRED WITH NO MESSAGE is the normal outcome, NOT an error. Raising would turn every quiet
            # minute into an error log line, and the polling loop with backoff would retreat forever although
            # the line is perfectly healthy. ``int(...)`` rather than strict comparison: ``error_code`` is
            # declared ``int | str`` because the documentation does not commit; today it is a number, but if
            # Zalo changed it to the string "408" a strict comparison would miss it and every quiet minute
            # would become an error log plus a 60 second retreat, the very consequence this branch exists to
            # avoid.
            if _as_int(err.ma_loi) == MA_LOI_HET_HAN_CHO:
                return None
            raise
        if not isinstance(kq, dict) or not cast(dict[str, Any], kq).get("event_name"):
            return None
        return ZaloBotUpdate.model_validate(kq)

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> KetQuaGuiTin:
        """Send text. Default ``parse_mode: None`` = PLAIN TEXT.

        The first version defaulted to ``"markdown"`` with a note "so the SERVER builds the formatting". That
        note described a flow that DOES NOT EXIST: the reply path runs the formatter first and
        ``markdown_sang_style_zalo`` strips the marks into a ``Style[]``, so there is no markdown left to
        build by here; asking the server can only REMOVE characters. No production caller used the old default
        (the bot channel always passes ``None`` explicitly), but a wrong default is a trap built for the next
        caller. To probe ``parse_mode``, pass it explicitly."""
        body: dict[str, object] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        return KetQuaGuiTin.model_validate(await self._goi("sendMessage", body) or {})

    async def send_photo(self, chat_id: str, photo_url: str, caption: str | None = None) -> KetQuaGuiTin:
        """Send a photo. ``photo_url`` MUST be a public ``http(s)://`` URL: Zalo fetches it from its side.

        Measured on the real API, all three alternatives are REJECTED: multipart/form-data ("The photo must
        not be empty"), a data URI and bare base64 ("The photo must start with http:// or https://").
        Consequence for ``create_image``: an image the bot drew cannot be sent directly, it needs a public
        HTTPS route first.

        Also: some hosts block Zalo's fetcher; ``picsum.photos`` and ``placehold.co`` worked, while
        ``upload.wikimedia.org`` answered "The photo URL is invalid" although the URL is HTTPS and opens in a
        browser."""
        body: dict[str, object] = {"chat_id": chat_id, "photo": photo_url}
        if caption:
            body["caption"] = caption
        return KetQuaGuiTin.model_validate(await self._goi("sendPhoto", body) or {})

    async def send_chat_action(self, chat_id: str, action: str = "typing") -> object:
        """The "typing" indicator. Zalo switches it off after a while, so call it again periodically."""
        return await self._goi("sendChatAction", {"chat_id": chat_id, "action": action})

    async def get_webhook_info(self) -> dict[str, Any]:
        result = await self._goi("getWebhookInfo")
        return cast(dict[str, Any], result) if isinstance(result, dict) else {}

    async def delete_webhook(self) -> object:
        """Webhook and getUpdates are MUTUALLY EXCLUSIVE (the documentation says "getUpdates will not work if
        a Webhook was set before"). A bot that long polls only needs this method to REMOVE a stray webhook."""
        return await self._goi("deleteWebhook")

    async def set_webhook(self, url: str, secret_token: str) -> object:
        """Webhook mode (new in Pema). ``url`` must be public HTTPS; ``secret_token`` is 8 to 256 characters
        and comes back in the ``X-Bot-Api-Secret-Token`` header of every delivery."""
        return await self._goi("setWebhook", {"url": url, "secret_token": secret_token})


class BotApiClient(Protocol):
    """The methods the channel, the runner, the listener and the admin service use. ``ZaloBotClient``
    implements it; tests pass a fake with the same shape (``zalo_bot.testing.FakeBotClient``)."""

    async def get_me(self) -> dict[str, Any]: ...

    async def get_updates(self, timeout_giay: int = 30) -> ZaloBotUpdate | None: ...

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> KetQuaGuiTin: ...

    async def send_chat_action(self, chat_id: str, action: str = "typing") -> object: ...

    async def get_webhook_info(self) -> dict[str, Any]: ...

    async def delete_webhook(self) -> object: ...

    async def set_webhook(self, url: str, secret_token: str) -> object: ...

    async def aclose(self) -> None: ...


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def tao_zalo_bot_client(
    token: str,
    *,
    goc_api: str = GOC_API_MAC_DINH,
    timeout_ms: int = 15_000,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ZaloBotClient:
    """``taoZaloBotClient``."""
    return ZaloBotClient(token, goc_api=goc_api, timeout_ms=timeout_ms, transport=transport)
