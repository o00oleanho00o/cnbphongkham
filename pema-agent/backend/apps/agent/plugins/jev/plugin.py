"""The jev plugin as the service and the admin page use it: its settings (model, the day's token
allowance), the TypeSafe key sealed in its own record, and what each day used. A call goes through
``judge``: it refuses when there is no key or the day's allowance is used up, otherwise it asks TypeSafe
and writes down what was used.

Shortcut: the allowance is checked before a call, not during it, so calls that run together can pass it by
one batch; the next call is refused. Upgrade when a batch could cost more than the allowance is worth."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent_app.plugins import JudgeUnavailableError, PluginContext, PluginError

from .client import JevClient, Meter

SETTINGS_KEY: Final = "settings"
KEY_RECORD: Final = "api_key"
USAGE_KEY: Final = "usage"
DEFAULT_MODEL: Final = "jev-latest"
DEFAULT_DAILY_TOKENS: Final = 2_000_000
MAX_DAILY_TOKENS: Final = 10_000_000_000
USD_PER_INPUT_TOKEN: Final = 42 / 1_000_000_000
"""TypeSafe's price at the time of writing: $42 per billion input tokens (nothing for output)."""
KEEP_DAYS: Final = 14
NO_KEY: Final = "Chưa có khóa TypeSafe. Nhập khóa ở trang Jev."


@dataclass(frozen=True, slots=True)
class Settings:
    model: str = DEFAULT_MODEL
    daily_token_cap: int = DEFAULT_DAILY_TOKENS
    """0 means no limit."""


@dataclass(slots=True)
class Day:
    calls: int = 0
    tokens: int = 0
    errors: int = 0

    def shown(self, day: str) -> dict[str, Any]:
        return {
            "date": day,
            "calls": self.calls,
            "tokens": self.tokens,
            "errors": self.errors,
            "usd": round(self.tokens * USD_PER_INPUT_TOKEN, 8),
        }


@dataclass(slots=True)
class _Book:
    days: dict[str, Day] = field(default_factory=dict[str, Day])


class JevPlugin:
    def __init__(self, ctx: PluginContext, *, client: JevClient | None = None) -> None:
        self._ctx = ctx
        self._client = client or JevClient()
        self._concurrency = max(1, min(64, int(ctx.config.get("concurrency", 8))))
        self._zone = _zone(str(ctx.config.get("timezone", "Asia/Ho_Chi_Minh")))
        self._writing = asyncio.Lock()

    async def settings(self) -> Settings:
        values = _mapping(await self._ctx.storage.get(SETTINGS_KEY))
        model = values.get("model")
        cap = values.get("daily_token_cap")
        return Settings(
            model=model if isinstance(model, str) and model else DEFAULT_MODEL,
            daily_token_cap=_count(cap, DEFAULT_DAILY_TOKENS),
        )

    async def save_settings(
        self, *, model: str | None, daily_token_cap: int | None, api_key: str | None
    ) -> None:
        """Raises ``PluginError`` when a key is given and the service has no secret key to seal it with."""
        if api_key is not None:
            await self._store_key(api_key.strip())
        current = await self.settings()
        await self._ctx.storage.put(
            SETTINGS_KEY,
            {
                "model": model if model is not None else current.model,
                "daily_token_cap": daily_token_cap
                if daily_token_cap is not None
                else current.daily_token_cap,
            },
        )

    async def has_key(self) -> bool:
        return await self._ctx.storage.get(KEY_RECORD) is not None

    async def ready(self) -> bool:
        key, _ = await self._key()
        if not key:
            return False
        cap = (await self.settings()).daily_token_cap
        return cap == 0 or (await self.today()).tokens < cap

    async def judge(
        self,
        states: Sequence[Any],
        questions: Mapping[str, Mapping[str, Any]],
        *,
        timeout_s: float,
    ) -> list[dict[str, Any]]:
        """The answers of each state; see ``agent_app.plugins.JudgeService.ask``."""
        key, broken = await self._key()
        if broken:
            raise JudgeUnavailableError(
                "Khóa TypeSafe đã lưu không giải mã được (khóa bí mật của agent đã đổi). Nhập lại khóa."
            )
        if not key:
            raise JudgeUnavailableError(NO_KEY)
        settings = await self.settings()
        used = (await self.today()).tokens
        if settings.daily_token_cap and used >= settings.daily_token_cap:
            raise JudgeUnavailableError(
                f"Đã dùng hết hạn mức {_dots(settings.daily_token_cap)} token hôm nay "
                f"({_dots(used)}). Đổi hạn mức ở trang Jev hoặc chờ sang ngày mai."
            )
        meter = Meter()
        failed = False
        try:
            return await self._client.ask_many(
                key=key,
                model=settings.model,
                states=states,
                questions=questions,
                timeout_s=timeout_s,
                concurrency=self._concurrency,
                meter=meter,
            )
        except JudgeUnavailableError:
            failed = True
            raise
        finally:
            await self._record(meter, failed=failed)

    async def today(self) -> Day:
        return (await self._book()).days.get(self._day(), Day())

    async def usage(self, days: int = 7) -> list[dict[str, Any]]:
        """The last days, newest first, today included even when nothing was used."""
        book = await self._book()
        names = sorted({self._day(), *book.days}, reverse=True)[:days]
        return [book.days.get(name, Day()).shown(name) for name in names]

    def _day(self) -> str:
        return datetime.now(UTC).astimezone(self._zone).date().isoformat()

    async def _book(self) -> _Book:
        raw = _mapping(await self._ctx.storage.get(USAGE_KEY))
        found = {name: _mapping(value) for name, value in raw.items()}
        return _Book(
            {
                name: Day(
                    calls=_count(value.get("calls")),
                    tokens=_count(value.get("tokens")),
                    errors=_count(value.get("errors")),
                )
                for name, value in found.items()
            }
        )

    async def _record(self, meter: Meter, *, failed: bool) -> None:
        async with self._writing:
            book = await self._book()
            day = book.days.setdefault(self._day(), Day())
            day.calls += meter.calls
            day.tokens += meter.tokens
            day.errors += 1 if failed else 0
            kept = sorted(book.days, reverse=True)[:KEEP_DAYS]
            await self._ctx.storage.put(
                USAGE_KEY,
                {
                    name: {"calls": d.calls, "tokens": d.tokens, "errors": d.errors}
                    for name, d in book.days.items()
                    if name in kept
                },
            )

    async def _key(self) -> tuple[str, bool]:
        """The key, and whether a stored one no longer decrypts (the service's secret key changed)."""
        sealed = await self._ctx.storage.get(KEY_RECORD)
        if not isinstance(sealed, str):
            return "", False
        try:
            return self._ctx.decrypt(sealed), False
        except PluginError:
            return "", True

    async def _store_key(self, key: str) -> None:
        if key:
            await self._ctx.storage.put(KEY_RECORD, self._ctx.encrypt(key))
        else:
            await self._ctx.storage.delete(KEY_RECORD)


def _mapping(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _count(value: Any, default: int = 0) -> int:
    return value if _is_count(value) else default


def _dots(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
