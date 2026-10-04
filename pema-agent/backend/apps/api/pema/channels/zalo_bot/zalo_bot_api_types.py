# ported from: src/zalo-bot/zalo-bot-api-types.ts
"""Types of the Zalo Bot API (``bot-api.zaloplatforms.com``).

THIS IS A DIFFERENT PRODUCT from the Zalo OA API (``openapi.zalo.me``); the two get mixed up everywhere,
including in third party documentation. The Bot API copies the shape of the Telegram Bot API: ``POST
/bot{token}/{method}``, a JSON body, an ``{ok, result}`` envelope. The "7 days since the last interaction"
policy and the message price list belong to the OA API and do NOT apply here; do not infer them.

Source: https://docs.zaloplatforms.com/docs/BOT  (webhook: https://bot.zapps.me/docs/webhook/)

Forced deviation: TypeScript object types become pydantic models that ACCEPT unknown fields
(``extra="allow"``) and make every field optional, because the payload shape is not guaranteed by Zalo and a
parser must not crash on a field that was renamed (the anomaly watch reports it instead). A webhook delivery
wraps the update as ``{"ok": true, "result": {event_name, message}}``; polling returns the inner object
directly (see ``unwrap_webhook_payload``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

LOAI_SU_KIEN: tuple[str, ...] = (
    "message.text.received",
    "message.image.received",
    "message.sticker.received",
    "message.voice.received",
    "message.unsupported.received",
)
"""The 5 event kinds a bot receives (webhook documentation)."""

TRAN_KY_TU_MOT_TIN = 2000
"""Cap of ONE message: the ``sendMessage`` documentation says "length from 1 to 2000 characters". Splitting is
the caller's job (``send_reply_in_parts``)."""


def _to_str(value: object) -> object:
    """Ids may arrive as numbers; keep them as text so a renamed type never rejects a whole update."""
    return value if value is None or isinstance(value, str) else str(value)


LooseStr = Annotated[str | None, BeforeValidator(_to_str)]


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ZaloBotFrom(_Loose):
    id: LooseStr = None
    display_name: str | None = None
    is_bot: bool | None = None


class ZaloBotChat(_Loose):
    id: LooseStr = None
    chat_type: str | None = None
    """PRIVATE = direct message, GROUP = group (groups are still internal beta on Zalo's side)."""


class ZaloBotMessage(_Loose):
    from_: ZaloBotFrom | None = Field(default=None, alias="from")
    chat: ZaloBotChat | None = None
    message_id: LooseStr = None
    date: float | None = None
    """MILLISECONDS since the epoch, NOT seconds like Telegram."""
    text: str | None = None
    photo: str | None = None
    """Image path. The documentation says ``photo``; the goclaw port reads ``photo_url`` as well."""
    photo_url: str | None = None
    caption: str | None = None
    sticker: str | None = None
    url: str | None = None
    voice_url: str | None = None


class ZaloBotUpdate(_Loose):
    event_name: str = ""
    message: ZaloBotMessage | None = None


class ZaloBotEnvelope(_Loose):
    """Envelope of every call.

    The failure branch, MEASURED ON THE REAL API: Zalo answers ``{ok: false, description, error_code}`` with
    HTTP **200**; ``description`` holds the reason, not ``message`` or ``error``. All three names are kept
    because the documentation does not commit to the shape. Real examples: ``{"ok":false,"description":"Bad
    request: The chat_id must not be empty","error_code":400}`` and ``{"ok":false,"description":"Not
    Found","error_code":404}``."""

    ok: bool | None = None
    result: Any = None
    description: str | None = None
    error: Any = None
    message: str | None = None
    error_code: int | str | None = None


class KetQuaGuiTin(_Loose):
    message_id: LooseStr = None
    date: float | None = None


def unwrap_webhook_payload(payload: Mapping[str, object]) -> dict[str, Any]:
    """Webhook bodies arrive as ``{"ok": true, "result": {"event_name": ..., "message": ...}}``, polling
    results as the inner object. Accept both so one parser serves both modes."""
    result = payload.get("result")
    if "event_name" not in payload and isinstance(result, dict):
        return {str(k): v for k, v in result.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return dict(payload)
