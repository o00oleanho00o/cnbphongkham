"""ECMAScript whitespace, shared by the modules that port JS ``trim()`` / ``\\s`` behaviour (no TS source).

Why a module of its own: ``channels/sanitize_reply_text`` (C2) and ``scheduler/silent_sentinel`` (S) must
treat the sentinel line ``[SILENT]`` the same way, and the original had ONE ``trim()``/``\\s`` for both.
Python's ``str.strip()`` / ``\\s`` is NOT the same set (JS includes U+FEFF; Python also matches
U+001C..U+001F and U+0085), so a copy per package drifted: ``"\\ufeff[SILENT]"`` was a sentinel
for one and not for the other.
``JS_WS_CHARS`` is the exact ECMAScript set; ``pema.channels.utf16_text`` re-exports these names.

Pure module: no imports of the application.
"""

from __future__ import annotations

# ECMAScript WhiteSpace + LineTerminator (ES2023 12.2, 12.3): TAB VT FF SP NBSP ZWNBSP + Zs, LF CR LS PS.
JS_WS_CHARS = "\t\n\x0b\x0c\r \xa0 " + "".join(chr(c) for c in range(0x2000, 0x200B)) + "    　﻿"

JS_S = f"[{JS_WS_CHARS}]"
"""Regex fragment for JS ``\\s``."""

JS_NOT_S = f"[^{JS_WS_CHARS}]"
"""Regex fragment for JS ``\\S``."""


def js_trim(text: str) -> str:
    """``String.prototype.trim``."""
    return text.strip(JS_WS_CHARS)


def js_trim_start(text: str) -> str:
    """``String.prototype.trimStart``."""
    return text.lstrip(JS_WS_CHARS)


def js_trim_end(text: str) -> str:
    """``String.prototype.trimEnd``."""
    return text.rstrip(JS_WS_CHARS)
