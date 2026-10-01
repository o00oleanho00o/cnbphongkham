# ported from: src/agent/agent-step-observer.ts
"""Everything that must be done AFTER each step of the agent loop: count for the anti-loop guard, log the
tools that ran and the tools that failed, collect the trace.

Forced deviations:

* Vercel AI SDK -> own loop: the handler takes a ``model_types.RawStep`` (the original reused its own
  ``RawStep`` type too).
* LOG CONTENT (clinic rule, AGENT.md: never log PII). The original logged the tool input and output
  (``forLog(..., 200/300)``), the step text, the reasoning and the tool error text. Here a tool input or
  output can hold a patient's words, so the log carries LENGTHS (``input_chars``, ``output_chars``,
  ``text_chars``, ``reasoning_chars``, ``error_chars``), tool names, codes, counters and the short
  behaviour-deciding arguments only; a file name is logged by its length. The FULL content is kept where
  it belongs: in the stored trace (``AGENT_TRACE_ENABLED``, retention ``AGENT_TRACE_RETENTION_DAYS``, RLS),
  which is the diagnosis surface. ``for_log`` is kept (same behaviour, tested) for callers that have
  already decided a value is safe to log.

Split from ``agent_loop`` because this is the OBSERVATION part, not the CONTROL part: it does not decide
whether the loop goes on or stops (the guard decides, through ``stopWhen``), it only reads and records.
Left tangled inside the model call the decider and the recorder overlap, and that file is already twice
the threshold.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pema.agent.agent_step_trace import summarize_step, thanh_chuoi
from pema.agent.model_types import RawStep
from pema.agent.tool_loop_guard import ToolLoopGuard
from pema.config.runtime_tuning_settings import get_tuning_bool, get_tuning_int
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import StepTrace

log = create_logger("agent-loop")


def for_log(value: object, max_chars: int) -> str:
    """Shorten a value for the log - a tool output (web page content) is thousands of chars long.

    ``JSON.stringify(undefined)`` returns undefined and not a string - reading ``.length`` of it is a
    TypeError (the SDK sets ``input: void 0`` for provider-run tools). In Python ``None`` is serialised as
    ``"null"`` (the JS ``undefined`` has no counterpart).

    The failed branch shows the SENTENCE instead of the JSON shell: the shell is both hard to read and eats
    ~20 chars of the 300 ceiling, and the part that gets cut is exactly the part saying why it failed.
    """
    text = thanh_chuoi(value)
    return f"{text[:max_chars]}..." if len(text) > max_chars else text


SHORT_FIELDS: tuple[str, ...] = (
    "mode",
    "imageIndex",
    "transparentBackground",
    "fileName",
    # snake_case spellings of the same arguments, for tools whose Python schema is snake_case
    "image_index",
    "transparent_background",
    "file_name",
)
"""SHORT fields that decide behaviour, logged separately so they are not cut off behind a long field. Hit
for real: the ``prompt`` of create_image was longer than the 200-char ceiling so the ``imageIndex`` standing
after it was swallowed whole - the diagnosis had to be deduced backwards from the error sentence instead of
being read directly."""

_TEN_FILE: frozenset[str] = frozenset({"fileName", "file_name"})
"""A file name can identify a patient: it is logged by length only (see the module docstring)."""


def _short_args_of(input_: object) -> dict[str, Any] | None:
    if not isinstance(input_, dict):
        return None
    record: dict[str, Any] = input_  # pyright: ignore[reportUnknownVariableType]
    picked: dict[str, Any] = {}
    for key in SHORT_FIELDS:
        if key not in record:
            continue
        if key in _TEN_FILE:
            picked[f"{key}_chars"] = len(str(record[key]))
        else:
            picked[key] = record[key]
    # The prompt length tells apart "the model copied the user's content verbatim" from "the model
    # summarised it into a topic" - two things that produce completely different images but cannot be told
    # apart from the first 200 chars
    prompt = record.get("prompt")
    if isinstance(prompt, str):
        picked["prompt_chars"] = len(prompt)
    return picked or None


def tao_quan_sat_step(
    *, guard: ToolLoopGuard, trace: list[StepTrace], lay_lan_chay: Callable[[], int]
) -> Callable[[RawStep], None]:
    """Build the handler for ``onStepFinish`` (the loop calls it after every step).

    ``lay_lan_chay`` is read AT CALL TIME and is not a number: the run number goes up in the middle of a
    turn (router glitch retry, rebuild without pixels); passing a number labels the traces of later runs
    with the first run's label and reads as the model looping forever.
    """

    def quan_sat(step: RawStep) -> None:
        # Record FIRST, before the tool logging below: the block decision must appear in the same log
        # cluster as the very step that caused it, not a step later.
        qd = guard.ghi_nhan(step)
        if qd.muc == "chan":
            log.error(
                f"Chặn vòng lặp tool: {qd.thong_diep} Dừng lượt và chốt lại bằng dữ liệu đã có.",
                tool=qd.tool,
                so_lan=qd.so_lan,
                ma=qd.ma,
            )
        elif qd.muc == "canh-bao":
            log.warning(qd.thong_diep, tool=qd.tool, so_lan=qd.so_lan, ma=qd.ma)

        for r in step.tool_results:
            log.info(
                "Tool đã chạy",
                tool=r.tool_name,
                input_chars=len(thanh_chuoi(r.input)),
                # A separate field, so it is not eaten by anything else
                args=_short_args_of(r.input),
                output_chars=len(thanh_chuoi(r.output)),
            )

        # A tool that RAN INTO AN ERROR never lands in ``tool_results``: it is a ``tool-error`` content
        # part. Before this loop, a schema rejecting an input or a tool raising an error left no trace at
        # all: empty log, the trace showed "Call tool" and stopped, while the model still received the
        # error and retried a few rounds - from outside the bot just seemed to promise and not deliver.
        # ERROR level because this is something that BROKE, not a diagnostic.
        for p in step.content:
            if p.type != "tool-error":
                continue
            error = p.error
            log.error(
                "Tool chạy lỗi",
                tool=p.tool_name,
                args=_short_args_of(p.input),
                error_type=type(error).__name__ if isinstance(error, BaseException) else None,
                error_chars=len(str(error) if isinstance(error, BaseException) else thanh_chuoi(error)),
            )

        if not get_tuning_bool("AGENT_TRACE_ENABLED"):
            return
        t = summarize_step(step, get_tuning_int("AGENT_TRACE_MAX_CHARS"), lay_lan_chay())
        trace.append(t)
        # DEBUG level because this is diagnostic data, turned on when needed and not poured into the normal
        # log. The original also logged the TOOL CALL (what the model sent) and the warnings (where the
        # provider says a parameter was silently ignored); here only their shape, see the module docstring.
        log.debug(
            "Chi tiết step agent",
            step=t.step_number,
            attempt=t.attempt,
            finish_reason=t.finish_reason,
            text_chars=len(step.text or ""),
            # Empty with OpenAI models (they do not expose the thinking string), filled with DeepSeek -
            # depends on the MODEL and not on configuration
            reasoning_chars=len(step.reasoning_text or ""),
            tool_calls=[c.get("name") for c in t.tool_calls],
            tool_results=[{"name": r.get("name"), "hong": bool(r.get("hong"))} for r in t.tool_results],
            tool_errors=[e.get("name") for e in t.tool_errors],
            warnings=t.warnings,
            tokens_in=t.input_tokens,
            tokens_out=t.output_tokens,
        )

    # Catch here instead of letting the SDK catch. ``notify()`` of ai@7.0.37 calls the callback in an EMPTY
    # ``try {...} catch (e) {}``, so an error here turns red nowhere: the guard stops counting, the trace
    # stops recording, and the log stays spotless. Wrap it so at least one ERROR line says the observation
    # part died from which step - and so ``run_agent_turn`` does not depend on whether the loop swallows it
    # (a later version changing that behaviour would kill the whole turn).
    def handler(step: RawStep) -> None:
        try:
            quan_sat(step)
        except Exception as exc:
            log.error("Quan sát step lỗi - guard và trace mất dữ liệu của step này", err=exc)

    return handler
