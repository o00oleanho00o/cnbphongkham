# ported from: src/agent/tool-call-signature.ts
"""Stable signature of a tool call: the basis for recognising "the same call as last time" in
``tool_loop_guard``.

Forced deviations (JS values to Python values): a JS ``bigint`` has no Python counterpart (``int`` is
unbounded, so it is written as a JSON number and still differs for different values); a JS ``Date`` /
``toJSON`` object becomes a Python ``datetime``/``date``/``time`` (``isoformat``) or any object with a
``toJSON()``/``to_json()`` method; ``Map``/``Set`` and other non-plain objects become ``"[object <type>]"``
exactly like ``Object.prototype.toString``; JS ``undefined``/function/symbol become ``null``, ``NaN`` and
``Infinity`` become ``null`` like ``JSON.stringify``. An integral float is written like a JS number
(``5.0`` -> ``5``, ``-0.0`` -> ``0``) so a value that went through a JSON round trip keeps its signature.

Kept apart because this is a concern independent of COUNTING: normalising JSON and hashing have their
own traps (order of nested keys, non-object values), and their own invariant to test (raw parameters must
never be exposed).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time
from typing import cast


def chuan_hoa_json(v: object, dang_duyet: set[int] | None = None) -> str:
    """Normalised JSON: keys sorted at EVERY level, no whitespace.

    AVOID THROWING AT ALL COSTS. This function runs in ``onStepFinish``, and the ``notify()`` of ai@7.0.37
    calls the callback in ``try { ... } catch (e) {}``, an EMPTY catch (read in
    ``node_modules/ai/dist/index.js``). A throw here does not make the turn go red: it is swallowed whole,
    the guard stops counting and the trace stops recording from that step on, and from outside everything
    still looks green. Silent failure is much harder to trace than loud failure.

    Three paths were closed, and to be honest they are NOT yet reachable with the repo's real data (tool
    input has been through the schema, no schema uses a date or bigint; tool output is only
    ``str | KetQuaLoiTool``). Closed because it is cheap and because this function is shared
    infrastructure, not because they were ever observed:

    * ``bigint``: ``JSON.stringify`` throws a TypeError straight away.
    * Circular references: unbounded recursion, stack overflow.
    * NON-PLAIN objects (Date, Map, Set): ``Object.entries`` returns nothing so every value of that kind
      hashes to ``{}``, and two different calls count as identical, the guard blocks wrongly. A Date goes
      through ``toJSON`` so it keeps its timestamp.

    The throwing path that is NOT closed, and this is the reachable one: the ``input`` of a ``tool-error``
    part is RAW JSON produced by the model, not yet through the schema; nested a few tens of thousands of
    levels deep it raises ``RecursionError`` (``RangeError`` in JS). Also a getter that throws and a
    ``toJSON`` that throws (not reachable with real data). All three are caught by the outer ``try/except``
    in ``tao_quan_sat_step``, the consequence wrapped up as the loss of the trace of exactly that step plus
    one ERROR line.
    """
    dang: set[int] = set() if dang_duyet is None else dang_duyet

    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _so_thuc(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if callable(v):
        return "null"

    vid = id(v)
    if vid in dang:
        return '"[vòng]"'
    dang.add(vid)
    try:
        if isinstance(v, list | tuple):
            return "[" + ",".join(chuan_hoa_json(x, dang) for x in cast("Sequence[object]", v)) + "]"

        if isinstance(v, Mapping):
            m = cast("Mapping[object, object]", v)
            cap = sorted(((str(k), val) for k, val in m.items()), key=lambda kv: kv[0])
            return (
                "{"
                + ",".join(
                    f"{json.dumps(k, ensure_ascii=False)}:{chuan_hoa_json(val, dang)}" for k, val in cap
                )
                + "}"
            )

        if isinstance(v, datetime | date | time):
            return json.dumps(v.isoformat(), ensure_ascii=False)
        to_json: Callable[[], object] | None = getattr(v, "toJSON", None) or getattr(v, "to_json", None)
        if callable(to_json):
            return chuan_hoa_json(to_json(), dang)
        return json.dumps(f"[object {type(v).__name__}]", ensure_ascii=False)
    finally:
        # Remove after the branch is done: the same object appearing twice in two PARALLEL branches is
        # legitimate, only a cycle is a problem.
        dang.discard(vid)


def _so_thuc(v: float) -> str:
    """A JS number: ``NaN``/``Infinity`` -> ``null``, an integral value without ``.0``, ``-0`` -> ``0``."""
    if not math.isfinite(v):
        return "null"
    if v == int(v):
        return str(int(v))
    return repr(v)


def bam_ngan(s: str) -> str:
    """First 16 chars of the SHA-256: enough not to collide within the scope of one turn."""
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def chu_ky_lenh_goi(ten_tool: str, args: object) -> str:
    """Signature of a call: tool name + hash of the normalised parameters.

    HASH rather than keep the raw parameters: the guard lives for the whole turn, and tool parameters hold
    what the user sent (file paths, questions, document content). Keeping them raw leaves private data in
    memory longer than needed, and makes it easy to leak into a log when someone prints the counters to
    diagnose.
    """
    return f"{ten_tool}#{bam_ngan(chuan_hoa_json({} if args is None else args))}"
