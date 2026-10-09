# ported from: src/zalo/zalo-client.ts (the seam only)
"""Python face of the Node bridge that keeps ``zca-js`` (``bridge/``).

Everything zalo-agent did with the zca-js ``API`` object goes through ``BridgeAccountApi``, one per account;
the lifecycle (start, stop, state, QR login) through ``BridgeClient``. Wire rules (full protocol in
``bridge/README.md``):

* camelCase fields zca-js itself defines (receipt params, quote, ``changed_profiles``) pass through unchanged;
  everything else is snake_case;
* a zca-js ``ZaloApiError`` carries a numeric ``code``: the bridge reports it only when the Zalo SERVER
  refused (nothing was delivered, a retry is safe); a transport failure has none;
* the Zalo credential travels only in the body of ``start_account`` and of the ``credential_updated`` event,
  signed, over loopback. Every request is signed; the secret and the credential are never logged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, cast

import httpx

from ..format.text_style import TextStyle
from .signing import signed_headers

JsonObject = dict[str, Any]


class ThreadKind(IntEnum):
    """zca-js ``ThreadType``: 0 = one-to-one, 1 = group."""

    USER = 0
    GROUP = 1


class ZaloBridgeError(Exception):
    """``kind``: ``zalo_rejected`` | ``transport`` | ``bridge_disabled`` | ``kill_switch`` | ``rate_limited``
    | ``not_running`` | ``blocked`` | ``bad_request`` | ``unauthorized``. ``code`` only for
    ``zalo_rejected``."""

    def __init__(self, kind: str, message: str, *, code: int | None = None) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.code = code


@dataclass(frozen=True)
class BridgeAccountState:
    account_id: str
    state: str
    """``stopped|connecting|connected|disconnected|session_dead|logged_out|blocked``."""
    own_id: str = ""


@dataclass(frozen=True)
class BridgeQrStatus:
    state: str
    """``idle|starting|waiting_scan|scanned|success|declined|error|timeout``."""
    qr_png_base64: str | None = None
    error: str | None = None


def _error_from(payload: Mapping[str, Any], status_code: int) -> ZaloBridgeError:
    error = payload.get("error")
    if isinstance(error, dict):
        fields = cast(dict[str, Any], error)
        code = fields.get("code")
        return ZaloBridgeError(
            str(fields.get("kind", "transport")),
            str(fields.get("message", "")),
            code=code if isinstance(code, int) and not isinstance(code, bool) else None,
        )
    return ZaloBridgeError("transport", f"unexpected bridge answer (HTTP {status_code})")


def _qr_status(payload: Mapping[str, Any]) -> BridgeQrStatus:
    qr = payload.get("qr_png_base64")
    error = payload.get("error")
    return BridgeQrStatus(
        state=str(payload.get("state", "idle")),
        qr_png_base64=qr if isinstance(qr, str) else None,
        error=error if isinstance(error, str) else None,
    )


class BridgeClient:
    """Signed HTTP client of the bridge, for one run of it (one base URL and secret)."""

    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.secret = secret
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self, method: str, path: str, body: JsonObject | None = None, *, params: dict[str, str] | None = None
    ) -> JsonObject:
        raw = b"" if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"content-type": "application/json", **signed_headers(self.secret, raw)}
        try:
            response = await self._http.request(method, path, content=raw, headers=headers, params=params)
        except httpx.HTTPError as err:
            raise ZaloBridgeError("transport", type(err).__name__) from None
        try:
            payload: object = response.json()
        except ValueError:
            raise ZaloBridgeError(
                "transport", f"non-JSON bridge answer (HTTP {response.status_code})"
            ) from None
        answer = cast(JsonObject, payload) if isinstance(payload, dict) else {}
        if response.status_code >= 400 or answer.get("ok") is not True:
            raise _error_from(answer, response.status_code)
        return answer

    async def health(self) -> bool:
        try:
            response = await self._http.get("/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def start_account(self, account_id: str, credential: JsonObject) -> str:
        """Logs in with the stored credential and starts the listener; the own uid."""
        payload = await self.request(
            "POST",
            f"/v1/accounts/{account_id}/start",
            {"credential": credential, "kill_switch": {"on": False, "scope": "proactive", "reason": None}},
        )
        return str(payload.get("own_id", ""))

    async def stop_account(self, account_id: str) -> None:
        await self.request("POST", f"/v1/accounts/{account_id}/stop", {})

    async def get_state(self, account_id: str) -> BridgeAccountState:
        payload = await self.request("GET", f"/v1/accounts/{account_id}/state")
        return BridgeAccountState(
            account_id=account_id,
            state=str(payload.get("state", "stopped")),
            own_id=str(payload.get("own_id", "")),
        )

    async def start_qr_login(self, account_id: str) -> BridgeQrStatus:
        return _qr_status(await self.request("POST", f"/v1/accounts/{account_id}/login/qr", {}))

    async def get_qr_login(self, account_id: str) -> BridgeQrStatus:
        return _qr_status(await self.request("GET", f"/v1/accounts/{account_id}/login/qr"))

    def account(self, account_id: str, own_id: str = "") -> BridgeAccountApi:
        return BridgeAccountApi(self, account_id, own_id)


class BridgeAccountApi:
    """The zca-js ``API`` of one account, over the bridge."""

    def __init__(self, client: BridgeClient, account_id: str, own_id: str) -> None:
        self._client = client
        self.account_id = account_id
        self.own_id = own_id

    def _path(self, suffix: str) -> str:
        return f"/v1/accounts/{self.account_id}/{suffix}"

    async def send_message(
        self,
        *,
        text: str,
        thread_id: str,
        thread_type: ThreadKind,
        styles: Sequence[TextStyle] = (),
        quote: JsonObject | None = None,
        proactive: bool = False,
    ) -> JsonObject:
        body: JsonObject = {
            "thread_id": thread_id,
            "thread_type": int(thread_type),
            "text": text,
            "proactive": proactive,
        }
        if styles:
            body["styles"] = [{"start": s.start, "len": s.length, "st": s.style} for s in styles]
        if quote is not None:
            body["quote"] = quote
        return await self._client.request("POST", self._path("send"), body)

    async def send_typing_event(self, thread_id: str, thread_type: ThreadKind) -> None:
        await self._client.request(
            "POST", self._path("typing"), {"thread_id": thread_id, "thread_type": int(thread_type)}
        )

    async def send_delivered_event(self, params: Sequence[JsonObject], thread_type: ThreadKind) -> None:
        await self._client.request(
            "POST",
            self._path("receipts/delivered"),
            {"is_seen": False, "params": list(params), "thread_type": int(thread_type)},
        )

    async def send_seen_event(self, params: Sequence[JsonObject], thread_type: ThreadKind) -> None:
        await self._client.request(
            "POST", self._path("receipts/seen"), {"params": list(params), "thread_type": int(thread_type)}
        )

    async def add_reaction(
        self, icon_key: str, *, msg_id: str, cli_msg_id: str, thread_id: str, thread_type: ThreadKind
    ) -> None:
        """``icon_key`` is a key of ``REACTION_ICONS``; the bridge maps it to the zca-js value."""
        await self._client.request(
            "POST",
            self._path("reaction"),
            {
                "icon_key": icon_key,
                "msg_id": msg_id,
                "cli_msg_id": cli_msg_id,
                "thread_id": thread_id,
                "thread_type": int(thread_type),
            },
        )
