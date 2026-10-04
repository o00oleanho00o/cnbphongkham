# ported from: src/agent/agent-step-trace.ts
"""Turn one step into a compact record for the log and the DB.

Forced deviations (Vercel AI SDK -> own loop): the step is ``model_types.RawStep`` (the original declared a
structural ``RawStep`` type of its own, now shared by every D1 module), and the result is the contract
class ``pema_contracts.agent_turn.StepTrace`` (pydantic, snake_case) whose ``tool_calls`` /
``tool_results`` / ``tool_errors`` items are dicts: ``{"name", "input"}``, ``{"name", "output"}`` (+
``"hong": True`` for the failed shape) and ``{"name", "error"}``. JS ``JSON.stringify`` is
``json.dumps(..., ensure_ascii=False, separators=(",", ":"))``; ``String(value)`` is ``str(value)``.

Why it exists: the first version only logged ``toolResults``, so when the bot did wrong nobody knew what
the model SENT to the tool, what it said between steps, or whether the provider silently dropped a
parameter. Paid for twice: the lottery-ticket lookup case had to go the long way round through the DB and
be reproduced by hand, the ``imageIndex`` case had to be deduced backwards from the error sentence.

PURE module: no env, no DB, receives the character ceiling ready-made. That way the tests run directly and
the truncation is checkable independently of storage.

About ``reasoning``: whether it exists is up to the MODEL, not the code. Measured through the router -
DeepSeek returns the whole thinking string even when not streaming, while OpenAI (gpt-5.6-sol) only returns
a one-line summary label when streaming and nothing when not streaming. The provider adapters already map
``reasoning_content`` to the reasoning text so here we only read ``reasoning_text``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from pema.agent.model_types import RawStep
from pema.agent.tools.tool_failure_result import la_ket_qua_loi
from pema_contracts.agent_turn import StepTrace


def cat(value: str, max_chars: int) -> str:
    """Cut WITH THE REAL LENGTH. Cutting silently with a bare ellipsis leaves the log reader not knowing
    whether 50 chars or 50,000 are being lost, and that is exactly what one needs to know when suspecting
    the model received incomplete data."""
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... ({len(value)} ký tự)"


def thanh_chuoi(value: object) -> str:
    """A SAFE ``JSON.stringify``: a tool input may hold a cycle or something unserialisable.

    The failed branch of a tool has its own convention (``{ok: False, loi}``) - show the SENTENCE, not the
    shell. Letting ``json.dumps`` handle it makes the Trace page show
    ``{"ok":false,"loi":"Không đọc được trang \\"x\\"..."}`` with the quotes escaped twice, exactly the box
    the operator opens to understand why the bot answered badly.
    """
    if isinstance(value, str):
        return value
    if la_ket_qua_loi(value):
        return f"LỖI: {value['loi']}"
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError, OverflowError):
        return str(value)


def _loi_thanh_chuoi(err: object) -> str:
    """Force an error into a readable sentence. NOT ``thanh_chuoi`` straight: in JS the ``message`` and
    ``stack`` of an Error are non-enumerable so ``JSON.stringify(err)`` gives ``{}`` - exactly the thing to
    read back is the thing lost. Zod reports schema errors as an array of issues so the JSON branch is
    still needed for the non-Error case."""
    if isinstance(err, BaseException):
        return str(err) or type(err).__name__
    if isinstance(err, str):
        return err
    return thanh_chuoi(err)


def _warning_thanh_chuoi(w: object) -> str:
    """An SDK warning is a full-shaped object - force it into a sentence a person can read."""
    if isinstance(w, str):
        return w
    if isinstance(w, Mapping):
        o = cast("Mapping[str, Any]", w)
        phan = [str(x) for x in (o.get("type"), o.get("setting"), o.get("message"), o.get("details")) if x]
        if phan:
            return " - ".join(phan)
    return thanh_chuoi(cast("object", w))


def summarize_step(step: RawStep, max_chars: int, attempt: int = 1) -> StepTrace:
    """``summarizeStep``. ``attempt`` is the run number WITHIN the same turn: a retry turn (router returned
    empty) or a rebuild without pixels both number the steps from 1 again, so the trace of one turn can be
    1,2,3 then 1,2,3 - sorted by step_number it reads 1,1,2,2,3,3 and looks exactly like the model looping
    forever. This column tells the two runs apart."""
    tool_results: list[dict[str, Any]] = []
    for r in step.tool_results:
        item: dict[str, Any] = {"name": r.tool_name or "?", "output": cat(thanh_chuoi(r.output), max_chars)}
        # ``hong`` = the FAILED branch of a tool (``ket_qua_loi``), not a normal result. It needs its OWN
        # flag rather than letting the UI sniff the "LỖI: " prefix in ``output``: a rule based on words is
        # blind after one word changes, exactly what ``tool_failure_result`` exists to avoid. Without this
        # flag every real BUSINESS failure (web_fetch dead, web_search empty, image quota used up) shows on
        # the Trace page exactly like a success, while the red "Tool failed" block only reads
        # ``tool_errors``, which this repo almost never produces.
        #
        # The ``tool_results`` column stores JSON so adding the field needs NO migration; an old record
        # missing the field has ``hong`` absent and the UI treats it as not failed.
        if la_ket_qua_loi(r.output):
            item["hong"] = True
        tool_results.append(item)

    return StepTrace(
        attempt=attempt,
        # The SDK numbers from 0; convert to count-from-1 RIGHT HERE so the log, the DB and the UI show
        # one number. Converting only in the UI makes reading the log back off by one.
        step_number=(step.step_number or 0) + 1,
        text=cat(step.text or "", max_chars),
        reasoning=cat(step.reasoning_text or "", max_chars),
        tool_calls=[
            {"name": c.tool_name or "?", "input": cat(thanh_chuoi(c.input), max_chars)}
            for c in step.tool_calls
        ],
        tool_results=tool_results,
        # A tool that RAN INTO AN ERROR never lands in ``tool_results``: it is a ``tool-error`` content part.
        tool_errors=[
            {"name": p.tool_name or "?", "error": cat(_loi_thanh_chuoi(p.error), max_chars)}
            for p in step.content
            if p.type == "tool-error"
        ],
        finish_reason=step.finish_reason or "",
        # Warnings are where the provider reports an ignored parameter - exactly the kind of fault hit 2
        # times (``size`` ignored by the model, ``quality`` never sent)
        warnings=[_warning_thanh_chuoi(w) for w in step.warnings],
        input_tokens=(step.usage.input_tokens or 0) if step.usage is not None else 0,
        output_tokens=(step.usage.output_tokens or 0) if step.usage is not None else 0,
    )
