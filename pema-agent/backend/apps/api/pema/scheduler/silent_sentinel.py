# ported from: src/scheduler/silent-sentinel.ts
"""Recognise the ``[SILENT]`` sentinel in the answer of a scheduled agent turn: a "watch for news" job (for
example "every morning at 7 summarise the tech news") does not always have something to report, and
messaging "nothing new" every morning is more annoying than silence.

Copies the ``_is_cron_silence_response`` rule of Hermes (``cron/scheduler.py``) with a narrower token set:
Hermes also accepts the variants without brackets SILENT/NO_REPLY because the model sometimes dropped the
brackets (issues #51438, #46917). This project teaches the model exactly one form "[SILENT]" in the prompt
(see ``CRON_HINT`` in ``scheduled_job_prompt``) so only that token is recognised: adding variants Hermes saw
and we have not observed would be defence against a problem that never happened.

PURE module: no DB, no env, no logger.
"""

from __future__ import annotations

import re

from pema.shared.js_whitespace import JS_S, js_trim

_JS_S_PLUS = re.compile(f"{JS_S}+")

SILENT_TOKEN = "[SILENT]"  # noqa: S105 - a sentinel string, not a credential


def _is_exact_token(line: str) -> bool:
    """A (trimmed) line that contains ONLY the token; inner whitespace does not count (``[ SILENT ]`` still
    matches)."""
    return _JS_S_PLUS.sub("", js_trim(line).upper()) == SILENT_TOKEN


def la_dong_sentinel(line: str) -> bool:
    """Is this line ONLY the sentinel label.

    A different LEVEL from ``is_silent_response`` below: that one judges the WHOLE answer (hence the rule "an
    answer that STARTS with [SILENT] is swallowed whole"), this one looks at ONE line. Using the wrong level
    loses content: filtering line by line with ``is_silent_response`` would throw away "[SILENT] là nhãn nội
    bộ, dùng để bot im lặng ạ" - a valid answer when the user asks about the label itself.
    """
    return _is_exact_token(line)


def is_silent_response(text: str) -> bool:
    """Should this answer be SWALLOWED (not sent). Accepts when:

    * the whole answer (trimmed) is only "[SILENT]";
    * "[SILENT]" stands ALONE on the first or last line (other lines with content are fine, for example
      "2 tin mới đã lọc xong\\n\\n[SILENT]" is valid if the model forgot to delete the label);
    * the answer STARTS with "[SILENT]" (the form "[SILENT] Không có gì mới hôm nay").

    A token in the MIDDLE of a sentence is STILL SENT: "mình định [SILENT] nhưng đây là tóm tắt hôm nay: ..."
    has to arrive; a real answer must not be swallowed by mistake.
    """
    stripped = js_trim(text)
    if not stripped:
        return False

    if _is_exact_token(stripped):
        return True

    lines = [ln for ln in re.split(r"\r?\n", stripped) if js_trim(ln) != ""]
    if lines and (_is_exact_token(lines[0]) or _is_exact_token(lines[-1])):
        return True

    return stripped.upper().startswith(SILENT_TOKEN)
