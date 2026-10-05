# ported from: src/agent/tools/tool-failure-result.ts
"""Convention that marks "this tool call FAILED" in a way a machine can read.

Why it exists: the repo decided early that **a tool does not raise into the agent loop**: every failing
branch is caught and a natural-language sentence is returned for the model to interpret. That is the right
decision (the model copes better with "this page blocks bots" than with a dead turn), but it has a side
effect nobody noticed: the Vercel AI SDK only produced a ``tool-error`` part when ``execute`` THREW. A
tool that returns a string always came out as a ``tool-result``, even when the string said it had failed.
The same holds for the hand-written loop of this port (D1): an exception is not a normal tool result.

So the failure counter of ``tool-loop-guard`` was almost dead code. Measured: the model calls
``web_fetch`` failing on 8 different URLs, or ``web_search`` empty on 8 different keywords, and the guard
did NOT stop it: the most expensive case was exactly where it was mute.

The cure is to teach the tool layer to say it failed, instead of making the guard guess from Vietnamese
sentences (Hermes sniffs strings in ``classify_tool_failure``; then changing one word in a message blinds
the guard again and no test goes red).

Why an OBJECT and not a string prefix such as ``"[LỖI] ..."``: web content / messages composed by
strangers go straight into the result string, so any rule based on words inside the string can be crafted
to match. A dict shape cannot be faked by content: content always sits in a FIELD, never in the envelope.

The model reads ``{"ok": false, "loi": "..."}`` no differently from a plain sentence, yet knows for sure
it is the failing branch.

PURE module: no log, no env, no DB.

Forced deviation: the TS ``type`` guard becomes a ``TypeGuard`` over a ``TypedDict``. The wire shape is
the same JSON object, so ``json.dumps(ket_qua_loi("x"))`` equals the original ``JSON.stringify``."""

from __future__ import annotations

from typing import Literal, TypedDict, TypeGuard


class KetQuaLoiTool(TypedDict):
    ok: Literal[False]
    """Always ``False``. This very field is the marker, not the words in ``loi``."""
    loi: str
    """The sentence for the model to read: still natural Vietnamese as before."""


def ket_qua_loi(thong_diep: str) -> KetQuaLoiTool:
    """Wrap a failure sentence into a marked tool result.

    Use it at EVERY failing branch of every tool. A successful branch still returns a bare string as
    before: there is nothing to mark, and keeping it means a turn that ran well is unchanged.

    Is an EMPTY result a failure or a success? Rule: empty but CERTAIN is success; empty and NOT
    DISTINGUISHABLE from a failure is a failure.

    * ``schedule_task list`` with no job -> a bare string. The store answers definitively: this thread has
      no job. Calling again gives the same, and that is the right answer for the user.
    * ``web_search`` with no result -> ``ket_qua_loi``. The provider chain swallows errors and returns an
      empty list, so "empty" can be both "nothing exists" and "every search service is down". When it
      cannot be told apart it must count as a failure: 8 keywords all empty is the loop to stop."""
    return {"ok": False, "loi": thong_diep}


def la_ket_qua_loi(ket_qua: object) -> TypeGuard[KetQuaLoiTool]:
    """Is this result a failing branch. Looks at the SHAPE only: no word sniffing, no guessing by tool name.

    It checks BOTH ``loi`` and ``ok`` rather than ``ok`` alone: the repo has other types of the same
    ``{ok: False, ...}`` shape with different field names (``LimitCheck``/``RateCheck`` use ``reason``,
    ``parse_schedule`` uses ``error``). Checking only ``ok`` would let a slip ``return limit`` (instead of
    ``ket_qua_loi(limit.reason)``) through: the guard counts correctly so no guard test goes red, while
    the model receives an object whose instruction sits under a key it was not told to read."""
    if not isinstance(ket_qua, dict):
        return False
    ok = ket_qua.get("ok")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    loi = ket_qua.get("loi")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return ok is False and isinstance(loi, str)
