# ported from: src/config/runtime-tuning-settings.ts (public API; first version by package A)
"""Effective value of the tuning parameters: an override (entered on the admin screen) wins over the
environment, which wins over the default of ``tuning_specs``.

THIS FILE IS THE CROSS-PACKAGE API: ``get_tuning`` is called from 55 files of the original (history store,
scheduler, channels, tools, knowledge, mcp, ...). Its signature is therefore FIXED by package A so every
package can code and test against it before D1 lands:

* ``get_tuning(key) -> TuningValue`` : synchronous, cheap, never raises for a known key;
* ``bot_time_zone() -> str``          : the most-read parameter (18 call sites in the original); one function
  so no call site reads the environment and forgets that the admin screen may have changed the zone;
* ``install_tuning_provider(provider)`` / ``reset_tuning_provider()`` : how D1's DB-backed provider (and
  tests) plug in.

Forced deviation (SQLite -> Postgres, sync -> async): the original read ``runtime_settings`` synchronously on
EVERY call ("reading again each time is the whole point of putting it on the web"). Python cannot await in a
plain call, so the override source is a ``TuningProvider`` that D1 backs with a short-lived in-memory
snapshot of ``agent.runtime_settings`` (refreshed on write and on a timer, a few seconds at most). A changed
value therefore still takes effect without a restart; it just is not instantaneous. The default provider
here has no overrides, so before D1 lands behaviour is "environment, then default".

Validation on READ is kept: a bad stored value is ignored (falls back) instead of killing the bot.
Booleans are the string ``"true"``; enums must be one of ``options``; a time zone must be valid (a broken
zone that slipped in by hand-editing the DB would make luxon fall back to UTC silently, shifting every
schedule by 7 hours); numbers must be finite and inside ``[min, max]``.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from typing import Protocol

from pema.config.tuning_specs import TUNING_SPECS, TuningSpec, TuningValue
from pema.shared.current_datetime import is_valid_timezone


class UnknownTuningKeyError(KeyError):
    """The key is not one of the 72 tuning parameters."""


class TuningProvider(Protocol):
    def override(self, key: str) -> str | None:
        """Raw stored override for ``key`` (the string as saved), or ``None`` when there is none."""
        ...


class _NoOverrides:
    def override(self, key: str) -> str | None:
        return None


class StaticTuningProvider:
    """Overrides from a dict. For tests and for D1's snapshot (which swaps the dict atomically)."""

    def __init__(self, overrides: Mapping[str, str | int | float | bool] | None = None) -> None:
        self._overrides: dict[str, str] = {}
        self.replace(overrides or {})

    def replace(self, overrides: Mapping[str, str | int | float | bool]) -> None:
        self._overrides = {k: _to_raw(v) for k, v in overrides.items()}

    def override(self, key: str) -> str | None:
        return self._overrides.get(key)


def _to_raw(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


_provider: TuningProvider = _NoOverrides()


def install_tuning_provider(provider: TuningProvider) -> None:
    global _provider
    _provider = provider


def reset_tuning_provider() -> None:
    install_tuning_provider(_NoOverrides())


def _parse(spec: TuningSpec, raw: str) -> TuningValue | None:
    """Parse ``raw`` for ``spec``; ``None`` when it is not valid (the caller then falls back)."""
    if spec.kind == "boolean":
        return raw == "true"
    if spec.kind == "enum":
        return raw if raw in spec.options else None
    if spec.kind == "timezone":
        return raw if is_valid_timezone(raw) else None
    try:
        number = float(raw)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    if (spec.minimum is not None and number < spec.minimum) or (
        spec.maximum is not None and number > spec.maximum
    ):
        return None
    if isinstance(spec.default, int) and number.is_integer():
        return int(number)
    return number


def _env_or_default(key: str, spec: TuningSpec) -> TuningValue:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return spec.default
    if spec.kind == "boolean":
        return raw.strip().lower() in {"true", "1", "yes", "on"}
    parsed = _parse(spec, raw)
    return spec.default if parsed is None else parsed


def tuning_default(key: str) -> TuningValue:
    """Value WHEN NO override exists: the environment if set, else the default (``macDinh``)."""
    spec = TUNING_SPECS.get(key)
    if spec is None:
        raise UnknownTuningKeyError(key)
    return _env_or_default(key, spec)


def get_tuning(key: str) -> TuningValue:
    """Effective value. A corrupt stored value is ignored rather than killing the bot."""
    spec = TUNING_SPECS.get(key)
    if spec is None:
        raise UnknownTuningKeyError(key)
    fallback = _env_or_default(key, spec)
    raw = _provider.override(key)
    if raw is None:
        return fallback
    parsed = _parse(spec, raw)
    return fallback if parsed is None else parsed


def get_tuning_int(key: str) -> int:
    """``get_tuning`` for a number parameter, as an int (most of them are counts or milliseconds)."""
    value = get_tuning(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} is not a number parameter")
    return int(value)


def get_tuning_bool(key: str) -> bool:
    value = get_tuning(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} is not a boolean parameter")
    return value


def bot_time_zone() -> str:
    """Effective time zone. One function because it is read from the most places (see module docstring)."""
    value = get_tuning("BOT_TIMEZONE")
    return value if isinstance(value, str) else str(TUNING_SPECS["BOT_TIMEZONE"].default)
