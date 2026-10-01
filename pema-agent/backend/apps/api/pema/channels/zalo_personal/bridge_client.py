# ported from: src/zalo/zalo-client.ts, src/zalo/zalo-credential-store.ts, src/zalo/zalo-listener.ts (the
# seam only)
"""Python face of the Node bridge that keeps ``zca-js`` (backend/bridges/zalo-personal).

``zca-js`` is NOT ported: it stays in Node behind a flag (PORT-MAP dependency table). Everything the original
did with the zca-js ``API`` object (``api.sendMessage``, ``api.sendTypingEvent``, ``api.addReaction``,
``api.getAllFriends`` ...) goes through ``ZaloApi`` below, one object per account. The ported modules take a
``ZaloApi`` exactly where the original took ``api: API``, so their shape and their tests stay recognisable
and tests inject a fake.

Wire rules (the full protocol is in the README of the bridge):

* camelCase fields that zca-js itself defines (receipt params, quote, ``changed_profiles``) are passed through
  unchanged; everything else is snake_case;
* a zca-js ``ZaloApiError`` carries a numeric ``code``; a transport failure does not. The bridge reports
  ``error.code`` (int) only for the first kind, and ``ZaloBridgeError.code`` mirrors it, which is what
  ``la_loi_may_chu_tu_choi`` (send_reply_in_parts) tests, exactly like the original;
* secrets (the Zalo credential) travel only in the body of ``start_account`` and of the ``credential_updated``
  event, signed with HMAC-SHA256 (``PEMA_ZALO_BRIDGE_SECRET``), over loopback or a private network. The bridge
  keeps them in memory and never writes them to disk;
* every request is signed (``bridge_signing``); the secret and the credential are never logged.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict, cast, runtime_checkable

import httpx

from pema.channels.zalo_personal.bridge_signing import signed_headers
from pema_contracts.channel import QuoteRef, TextStyle, ThreadKind
from pema_contracts.common import JsonObject


class ReceiptParams(TypedDict):
    """One message of a delivered/seen receipt: the nine fields zca-js ``sendSeenEvent`` needs."""

    msgId: str
    cliMsgId: str
    uidFrom: str
    idTo: str
    msgType: str
    st: int
    at: int
    cmd: int
    ts: str | int


class ZaloBridgeError(Exception):
    """A call to the bridge failed.

    ``code`` is the numeric zca-js ``ZaloApiError.code`` when the Zalo SERVER answered and refused (so nothing
    was delivered and a retry is safe), ``None`` for transport errors, timeouts and bridge-side refusals
    (where the outcome is unknown or the call never left). ``kind`` is a short machine word:
    ``zalo_rejected`` | ``transport`` | ``bridge_disabled`` | ``kill_switch`` | ``rate_limited`` |
    ``not_running`` | ``blocked`` | ``bad_request`` | ``unauthorized``.
    """

    def __init__(self, kind: str, message: str, *, code: int | None = None) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.code = code


@runtime_checkable
class ZaloApi(Protocol):
    """The subset of the zca-js ``API`` the ported modules use, bound to ONE account."""

    @property
    def account_id(self) -> str: ...

    def get_own_id(self) -> str:
        """``api.getOwnId()``: the uid of the logged-in account (``self_id`` in the original)."""
        ...

    async def send_message(
        self,
        *,
        text: str,
        thread_id: str,
        thread_type: ThreadKind,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        mentions: Sequence[JsonObject] = (),
        proactive: bool = False,
    ) -> JsonObject:
        """``api.sendMessage({msg, styles?, quote?, mentions?}, threadId, threadType)``. ``mentions`` are the
        zca-js ``{pos, uid, len}`` entries (``tag_member``). ``proactive`` tells the bridge the message
        is not a
        reply, so its kill switch and its own hard ceiling apply."""
        ...

    async def send_typing_event(self, thread_id: str, thread_type: ThreadKind) -> None: ...

    async def send_delivered_event(
        self, is_seen: bool, params: Sequence[ReceiptParams], thread_type: ThreadKind
    ) -> None: ...

    async def send_seen_event(self, params: Sequence[ReceiptParams], thread_type: ThreadKind) -> None: ...

    async def add_reaction(
        self, icon_key: str, *, msg_id: str, cli_msg_id: str, thread_id: str, thread_type: ThreadKind
    ) -> None:
        """``icon_key`` is a key of ``REACTION_ICONS``; the bridge maps it to the zca-js ``Reactions``
        value."""
        ...

    async def get_user_info(self, uid: str) -> JsonObject:
        """``{"changed_profiles": {uid: {displayName, zaloName, avatar, ...}}}`` as zca-js returns it."""
        ...

    async def get_all_friends(self) -> list[JsonObject]: ...

    async def accept_friend_request(self, uid: str) -> None: ...

    async def reject_friend_request(self, uid: str) -> None: ...

    async def get_group_info(self, thread_id: str) -> JsonObject: ...

    async def send_attachment(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        filename: str,
        data: bytes,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject: ...

    async def send_video(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        video_url: str,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject: ...


def thread_type_to_wire(kind: ThreadKind) -> int:
    """zca-js ``ThreadType``: 0 = direct, 1 = group."""
    return 1 if kind is ThreadKind.GROUP else 0


# ----------------------------------------------------------------------------------------------- gateway


@dataclass(frozen=True)
class KillSwitchState:
    on: bool
    scope: Literal["proactive", "all"] = "proactive"
    reason: str | None = None


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


@runtime_checkable
class BridgeGateway(Protocol):
    """Lifecycle operations of the bridge (not bound to one account's ``ZaloApi``). Implemented by
    ``HttpBridgeClient``; tests use a fake."""

    async def start_account(
        self, account_id: str, *, clinic_slug: str, credential: JsonObject, kill_switch: KillSwitchState
    ) -> str:
        """Log in with the stored credential and start the listener. Returns the own uid."""
        ...

    async def stop_account(self, account_id: str) -> None: ...

    async def stop_all(self) -> None: ...

    async def get_state(self, account_id: str) -> BridgeAccountState: ...

    async def start_qr_login(self, account_id: str, *, clinic_slug: str) -> BridgeQrStatus: ...

    async def get_qr_login(self, account_id: str) -> BridgeQrStatus: ...

    async def set_kill_switch(self, state: KillSwitchState) -> None: ...

    def account_api(self, account_id: str, own_id: str = "") -> ZaloApi: ...


def _wire_styles(styles: Sequence[TextStyle]) -> list[dict[str, int | str]]:
    return [{"start": s.start, "len": s.length, "st": s.style} for s in styles]


def _error_from(payload: object, status_code: int) -> ZaloBridgeError:
    body = cast("dict[str, object]", payload) if isinstance(payload, dict) else {}
    error = body.get("error")
    if isinstance(error, dict):
        fields = cast("dict[str, object]", error)
        kind = str(fields.get("kind", "transport"))
        message = str(fields.get("message", ""))
        code = fields.get("code")
        return ZaloBridgeError(
            kind, message, code=code if isinstance(code, int) and not isinstance(code, bool) else None
        )
    return ZaloBridgeError("transport", f"unexpected bridge answer (HTTP {status_code})")


def _qr_status(payload: JsonObject) -> BridgeQrStatus:
    qr = payload.get("qr_png_base64")
    error = payload.get("error")
    return BridgeQrStatus(
        state=str(payload.get("state", "idle")),
        qr_png_base64=qr if isinstance(qr, str) else None,
        error=error if isinstance(error, str) else None,
    )


class HttpBridgeClient:
    """Signed HTTP client of the Node bridge. One instance per process; ``account_api`` gives the per-account
    ``ZaloApi`` the ported modules use."""

    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._secret = secret
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self, method: str, path: str, body: JsonObject | None = None, *, params: dict[str, str] | None = None
    ) -> JsonObject:
        raw = b"" if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"content-type": "application/json", **signed_headers(self._secret, raw)}
        try:
            response = await self._client.request(method, path, content=raw, headers=headers, params=params)
        except httpx.HTTPError as err:
            # The outcome of the call is unknown: never a numeric code, so nothing is retried upstream.
            raise ZaloBridgeError("transport", type(err).__name__) from err
        try:
            payload: object = response.json()
        except ValueError:
            raise ZaloBridgeError(
                "transport", f"non-JSON bridge answer (HTTP {response.status_code})"
            ) from None
        answer: JsonObject = cast("JsonObject", payload) if isinstance(payload, dict) else {}
        if response.status_code >= 400 or answer.get("ok") is not True:
            raise _error_from(answer, response.status_code)
        return answer

    # -- BridgeGateway

    async def start_account(
        self, account_id: str, *, clinic_slug: str, credential: JsonObject, kill_switch: KillSwitchState
    ) -> str:
        payload = await self.request(
            "POST",
            f"/v1/accounts/{account_id}/start",
            {
                "clinic_slug": clinic_slug,
                "credential": credential,
                "kill_switch": {
                    "on": kill_switch.on,
                    "scope": kill_switch.scope,
                    "reason": kill_switch.reason,
                },
            },
        )
        return str(payload.get("own_id", ""))

    async def stop_account(self, account_id: str) -> None:
        await self.request("POST", f"/v1/accounts/{account_id}/stop", {})

    async def stop_all(self) -> None:
        await self.request("POST", "/v1/accounts/stop-all", {})

    async def get_state(self, account_id: str) -> BridgeAccountState:
        payload = await self.request("GET", f"/v1/accounts/{account_id}/state")
        return BridgeAccountState(
            account_id=account_id,
            state=str(payload.get("state", "stopped")),
            own_id=str(payload.get("own_id", "")),
        )

    async def start_qr_login(self, account_id: str, *, clinic_slug: str) -> BridgeQrStatus:
        payload = await self.request(
            "POST", f"/v1/accounts/{account_id}/login/qr", {"clinic_slug": clinic_slug}
        )
        return _qr_status(payload)

    async def get_qr_login(self, account_id: str) -> BridgeQrStatus:
        return _qr_status(await self.request("GET", f"/v1/accounts/{account_id}/login/qr"))

    async def set_kill_switch(self, state: KillSwitchState) -> None:
        await self.request(
            "POST", "/v1/kill-switch", {"on": state.on, "scope": state.scope, "reason": state.reason}
        )

    def account_api(self, account_id: str, own_id: str = "") -> ZaloApi:
        return BridgeAccountApi(self, account_id, own_id)


class BridgeAccountApi:
    """``ZaloApi`` of one account, implemented over ``HttpBridgeClient``."""

    def __init__(self, client: HttpBridgeClient, account_id: str, own_id: str) -> None:
        self._client = client
        self._account_id = account_id
        self._own_id = own_id

    @property
    def account_id(self) -> str:
        return self._account_id

    def get_own_id(self) -> str:
        return self._own_id

    def _path(self, suffix: str) -> str:
        return f"/v1/accounts/{self._account_id}/{suffix}"

    async def send_message(
        self,
        *,
        text: str,
        thread_id: str,
        thread_type: ThreadKind,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        mentions: Sequence[JsonObject] = (),
        proactive: bool = False,
    ) -> JsonObject:
        body: JsonObject = {
            "thread_id": thread_id,
            "thread_type": thread_type_to_wire(thread_type),
            "text": text,
            "proactive": proactive,
        }
        # Only attach styles when non-empty and a quote only when present (see ``reply_target_from_channel``).
        if styles:
            body["styles"] = _wire_styles(styles)
        if quote is not None:
            body["quote"] = quote.raw
        if mentions:
            body["mentions"] = [dict(m) for m in mentions]
        return await self._client.request("POST", self._path("send"), body)

    async def send_typing_event(self, thread_id: str, thread_type: ThreadKind) -> None:
        await self._client.request(
            "POST",
            self._path("typing"),
            {"thread_id": thread_id, "thread_type": thread_type_to_wire(thread_type)},
        )

    async def send_delivered_event(
        self, is_seen: bool, params: Sequence[ReceiptParams], thread_type: ThreadKind
    ) -> None:
        await self._client.request(
            "POST",
            self._path("receipts/delivered"),
            {"is_seen": is_seen, "params": list(params), "thread_type": thread_type_to_wire(thread_type)},
        )

    async def send_seen_event(self, params: Sequence[ReceiptParams], thread_type: ThreadKind) -> None:
        await self._client.request(
            "POST",
            self._path("receipts/seen"),
            {"params": list(params), "thread_type": thread_type_to_wire(thread_type)},
        )

    async def add_reaction(
        self, icon_key: str, *, msg_id: str, cli_msg_id: str, thread_id: str, thread_type: ThreadKind
    ) -> None:
        await self._client.request(
            "POST",
            self._path("reaction"),
            {
                "icon_key": icon_key,
                "msg_id": msg_id,
                "cli_msg_id": cli_msg_id,
                "thread_id": thread_id,
                "thread_type": thread_type_to_wire(thread_type),
            },
        )

    async def get_user_info(self, uid: str) -> JsonObject:
        payload = await self._client.request("GET", self._path("user-info"), params={"uid": uid})
        data = payload.get("data")
        return data if isinstance(data, dict) else {}  # pyright: ignore[reportUnknownVariableType]

    async def get_all_friends(self) -> list[JsonObject]:
        payload = await self._client.request("GET", self._path("friends"))
        friends = payload.get("friends")
        return [f for f in friends if isinstance(f, dict)] if isinstance(friends, list) else []  # pyright: ignore[reportUnknownVariableType]

    async def accept_friend_request(self, uid: str) -> None:
        await self._client.request("POST", self._path("friends/accept"), {"uid": uid})

    async def reject_friend_request(self, uid: str) -> None:
        await self._client.request("POST", self._path("friends/reject"), {"uid": uid})

    async def get_group_info(self, thread_id: str) -> JsonObject:
        payload = await self._client.request("GET", self._path("group-info"), params={"thread_id": thread_id})
        data = payload.get("data")
        return data if isinstance(data, dict) else {}  # pyright: ignore[reportUnknownVariableType]

    async def send_attachment(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        filename: str,
        data: bytes,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return await self._client.request(
            "POST",
            self._path("send-attachment"),
            {
                "thread_id": thread_id,
                "thread_type": thread_type_to_wire(thread_type),
                "filename": filename,
                "data_base64": base64.b64encode(data).decode("ascii"),
                "caption": caption,
                "proactive": proactive,
            },
        )

    async def send_video(
        self,
        *,
        thread_id: str,
        thread_type: ThreadKind,
        video_url: str,
        caption: str,
        proactive: bool = False,
    ) -> JsonObject:
        return await self._client.request(
            "POST",
            self._path("send-video"),
            {
                "thread_id": thread_id,
                "thread_type": thread_type_to_wire(thread_type),
                "video_url": video_url,
                "caption": caption,
                "proactive": proactive,
            },
        )
