# ported from: src/agent/stream-text-result.ts (and the ``streamText`` call of agent-loop.ts it wrapped)
"""The multi-step tool loop that replaces the Vercel AI SDK's ``streamText`` + ``stopWhen`` + ``prepareStep``
+
``onStepFinish`` + ``maxRetries`` + ``timeout.totalMs``, and returns the SHAPE ``generateText`` used to return
(``text``, ``steps``, ``total_usage``, ``finish_reason``, ``response``).

Why the agent turn goes through a STREAMING model call at all (the reason of the original file, kept): the
router sat behind a CDN that cut the connection with a 524 when the origin had not sent the FIRST BYTE within
100 s, and a non-stream request makes the router gather the whole answer before sending anything. Measured on
the project's router with the same ~4000-word prompt: ``stream=false`` -> HTTP 524 at second 125,
``stream=true``
-> HTTP 200, first byte at 7.5 s, done at 135 s. The adapters of ``pema.agent.providers`` therefore stream on
the
wire; nothing is ever streamed to the channel because this loop reads each call to the end.

Forced deviations from the original (own loop instead of the SDK):

* ``taoBoBatLoiStream`` / ``gomKetQuaStream`` existed because ``streamText`` SWALLOWED the original error and
  rejected its promises with a freshly built ``NoOutputGeneratedError``, and could even RESOLVE with a
  truncated
  result when step 2 failed after step 1 had been written. Here the loop is ours: an error raised by the model
  call or by anything else propagates as the ORIGINAL exception, a failure at step N after step N-1 finished
  raises (it never returns a truncated result), and every call of ``chay_stream`` has its own state, so the
  error of a previous run cannot kill a later, successful one. The behaviours the original pinned with tests
  are
  kept as tests in ``test_run_agent_turn`` (original error type and HTTP code survive, mid-turn failure
  raises,
  a failed attempt followed by a successful retry does not kill the turn, a previous run's error does not
  leak).
* ``maxRetries``: retry a model call that failed with a retryable error (408, 409, 429, 5xx, network) up to
  ``max_retries`` more times with exponential backoff (2 s, 4 s, ... or the provider's ``Retry-After`` when it
  is
  a sane number); never 400/401/403. The SDK wrapped the last error in ``RetryError("Failed after 3
  attempts")``;
  here the last error itself is raised (the classifier needs no unwrapping step).
* The SDK ran the tools of a step in parallel and turned an exception, an unknown tool name or invalid
  arguments
  into a ``tool-error`` content part that the model sees as an error result; that is kept. Arguments are
  checked
  only for being a JSON object here: validation against the tool's schema is the tool's own job (package D4).
* ``timeout.totalMs`` becomes ``asyncio.timeout`` around the whole loop; cancellation also reaches a running
  tool (the original's ``abortSignal``).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pema.agent.model_types import (
    ChatModel,
    ModelCompletion,
    ModelMessage,
    ModelRequest,
    ModelUsage,
    ProviderOptions,
    RawStep,
    StepContentPart,
    ToolCallPart,
    ToolResultPart,
    ToolSchema,
)
from pema.agent.providers.errors import is_retryable_error
from pema_contracts.tools import AgentTool

type StopCondition = Callable[[Sequence[RawStep]], bool]
"""``stopWhen`` entry: given every step so far, stop the loop?"""

type PrepareStep = Callable[[list[ModelMessage]], Awaitable[list[ModelMessage] | None]]
"""``prepareStep``: before EACH step (the first included) receive the current messages; return a new list to
override them (the override is carried forward to later steps) or ``None`` for no change."""

MAX_RETRY_AFTER_S = 60.0
"""A ``Retry-After`` above this is ignored (the SDK's rule): waiting longer than a turn lasts is no use."""


def step_count_is(count: int) -> StopCondition:
    """``stepCountIs(n)``."""
    return lambda steps: len(steps) >= count


@dataclass
class StreamTextResult:
    """The shape of ``generateText``'s result that ``agent_loop`` reads."""

    text: str
    steps: list[RawStep]
    total_usage: ModelUsage
    finish_reason: str
    model_id: str | None
    response_messages: list[ModelMessage] = field(default_factory=list[ModelMessage])
    """Every assistant and tool message the loop generated (``response.messages``): the wrap-up call replays
    them."""


def _retry_after_s(err: BaseException) -> float | None:
    headers: Any = getattr(err, "response_headers", None)
    if not isinstance(headers, Mapping):
        return None
    raw = headers.get("retry-after")  # type: ignore[reportUnknownMemberType]
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return seconds if 0 <= seconds <= MAX_RETRY_AFTER_S else None


async def _complete_with_retries(
    model: ChatModel,
    request: ModelRequest,
    *,
    max_retries: int,
    sleep: Callable[[float], Awaitable[None]],
    initial_delay_s: float,
    on_attempt_error: Callable[[BaseException], None] | None,
) -> ModelCompletion:
    attempt = 0
    while True:
        try:
            return await model.complete(request)
        except Exception as exc:
            # The failed attempt is logged even when a retry then succeeds (the original ``onError`` hook
            # did):
            # it is the only trace of a transient fault that the SDK's retries hid.
            if on_attempt_error is not None:
                on_attempt_error(exc)
            if attempt >= max_retries or not is_retryable_error(exc):
                raise
            delay = _retry_after_s(exc)
            await sleep(initial_delay_s * (2**attempt) if delay is None else delay)
            attempt += 1


def _tool_output_part(output: object) -> dict[str, Any]:
    if isinstance(output, str):
        return {"type": "text", "value": output}
    return {"type": "json", "value": output}


async def _run_one_tool(
    call: ToolCallPart, tools: Mapping[str, AgentTool]
) -> tuple[ToolResultPart | None, StepContentPart | None]:
    """Run one call. Returns ``(result, None)`` or ``(None, tool_error_part)``; never raises (except
    cancel)."""
    tool = tools.get(call.tool_name)
    if tool is None:
        return None, StepContentPart(
            type="tool-error",
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            input=call.input,
            error=f"Model tried to call unavailable tool '{call.tool_name}'.",
        )
    if call.invalid_input is not None:
        return None, StepContentPart(
            type="tool-error",
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            input=call.input,
            error=f"Invalid input for tool {call.tool_name}: {call.invalid_input}",
        )
    try:
        output = await tool.execute(call.input if isinstance(call.input, dict) else {})
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return None, StepContentPart(
            type="tool-error",
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            input=call.input,
            error=exc,
        )
    return ToolResultPart(
        tool_call_id=call.tool_call_id, tool_name=call.tool_name, input=call.input, output=output
    ), None


def _assistant_message(completion: ModelCompletion) -> ModelMessage | None:
    parts: list[dict[str, Any]] = list(completion.reasoning_parts)
    if completion.text:
        parts.append({"type": "text", "text": completion.text})
    for call in completion.tool_calls:
        part: dict[str, Any] = {
            "type": "tool-call",
            "toolCallId": call.tool_call_id,
            "toolName": call.tool_name,
            "input": call.input,
        }
        if call.provider_options:
            part["providerOptions"] = call.provider_options
        parts.append(part)
    return {"role": "assistant", "content": parts} if parts else None


def _error_text(err: object) -> str:
    if isinstance(err, BaseException):
        return str(err) or type(err).__name__
    return str(err)


async def _run_loop(
    *,
    model: ChatModel,
    system: str,
    messages: list[ModelMessage],
    tools: Mapping[str, AgentTool] | None,
    stop_when: Sequence[StopCondition],
    max_output_tokens: int | None,
    provider_options: ProviderOptions | None,
    headers: Mapping[str, str] | None,
    max_retries: int,
    request_timeout_s: float | None,
    on_step_finish: Callable[[RawStep], None] | None,
    prepare_step: PrepareStep | None,
    sleep: Callable[[float], Awaitable[None]],
    retry_initial_delay_s: float,
    on_attempt_error: Callable[[BaseException], None] | None,
) -> StreamTextResult:
    current = list(messages)
    steps: list[RawStep] = []
    generated: list[ModelMessage] = []
    total = ModelUsage()
    schemas = [ToolSchema(name, t.description, t.parameters) for name, t in (tools or {}).items()]

    while True:
        if prepare_step is not None:
            override = await prepare_step(current)
            if override is not None:
                current = override
        request = ModelRequest(
            system=system,
            messages=current,
            tools=schemas,
            max_output_tokens=max_output_tokens,
            provider_options=provider_options,
            headers=dict(headers or {}),
            timeout_s=request_timeout_s,
        )
        completion = await _complete_with_retries(
            model,
            request,
            max_retries=max_retries,
            sleep=sleep,
            initial_delay_s=retry_initial_delay_s,
            on_attempt_error=on_attempt_error,
        )

        content: list[StepContentPart] = []
        if completion.reasoning_text:
            content.append(StepContentPart(type="reasoning", text=completion.reasoning_text))
        if completion.text:
            content.append(StepContentPart(type="text", text=completion.text))
        for call in completion.tool_calls:
            content.append(
                StepContentPart(
                    type="tool-call",
                    tool_name=call.tool_name,
                    tool_call_id=call.tool_call_id,
                    input=call.input,
                )
            )

        outcomes = await asyncio.gather(*(_run_one_tool(c, tools or {}) for c in completion.tool_calls))
        results: list[ToolResultPart] = []
        tool_message_parts: list[dict[str, Any]] = []
        for call, (result, error) in zip(completion.tool_calls, outcomes, strict=True):
            if result is not None:
                results.append(result)
                content.append(
                    StepContentPart(
                        type="tool-result",
                        tool_name=call.tool_name,
                        tool_call_id=call.tool_call_id,
                        input=call.input,
                    )
                )
                output: dict[str, Any] = _tool_output_part(result.output)
            elif error is not None:
                content.append(error)
                output = {"type": "error-text", "value": _error_text(error.error)}
            else:  # pragma: no cover - _run_one_tool returns exactly one of the two
                continue
            tool_message_parts.append(
                {
                    "type": "tool-result",
                    "toolCallId": call.tool_call_id,
                    "toolName": call.tool_name,
                    "output": output,
                }
            )

        response_messages: list[ModelMessage] = []
        assistant = _assistant_message(completion)
        if assistant is not None:
            response_messages.append(assistant)
        if tool_message_parts:
            response_messages.append({"role": "tool", "content": tool_message_parts})

        step = RawStep(
            step_number=len(steps),
            text=completion.text,
            reasoning_text=completion.reasoning_text,
            tool_calls=list(completion.tool_calls),
            tool_results=results,
            content=content,
            finish_reason=completion.finish_reason,
            warnings=list(completion.warnings),
            usage=completion.usage,
            response_messages=response_messages,
        )
        steps.append(step)
        generated.extend(response_messages)
        current = [*current, *response_messages]
        total = total.plus(completion.usage)

        if on_step_finish is not None:
            # The SDK's ``notify`` called the callback inside an EMPTY try/catch, so an error in the observer
            # vanished; the observer (``taoQuanSatStep``) catches and logs itself, this only keeps a bug in a
            # callback from killing a turn that already got its answer.
            with contextlib.suppress(Exception):
                on_step_finish(step)

        if not completion.tool_calls:
            break
        if any(stop(steps) for stop in stop_when):
            break

    last = steps[-1]
    return StreamTextResult(
        text=last.text,
        steps=steps,
        total_usage=total,
        finish_reason=last.finish_reason,
        model_id=completion.model_id,
        response_messages=generated,
    )


async def chay_stream(
    *,
    model: ChatModel,
    system: str,
    messages: list[ModelMessage],
    tools: Mapping[str, AgentTool] | None = None,
    stop_when: Sequence[StopCondition] = (),
    max_output_tokens: int | None = None,
    provider_options: ProviderOptions | None = None,
    headers: Mapping[str, str] | None = None,
    max_retries: int = 2,
    timeout_s: float | None = None,
    request_timeout_s: float | None = None,
    on_step_finish: Callable[[RawStep], None] | None = None,
    prepare_step: PrepareStep | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retry_initial_delay_s: float = 2.0,
    on_attempt_error: Callable[[BaseException], None] | None = None,
) -> StreamTextResult:
    """THE way to run the model in this project (``chayStream``): one multi-step run with its own state.

    ``stop_when`` is checked after each step that still has tool calls (like the SDK, the tools of the last
    step have already run: the guard reads their results from ``on_step_finish`` and the caller's wrap-up call
    sees the step that was cut off). A step without tool calls always ends the run. ``timeout_s`` bounds the
    WHOLE run (``timeout.totalMs``); without it a router that accepts the connection and then hangs would hold
    the thread for the connection timeout x ``max_retries`` x steps while later messages queue behind it.
    """
    deadline = asyncio.timeout(timeout_s)
    try:
        async with deadline:
            return await _run_loop(
                model=model,
                system=system,
                messages=messages,
                tools=tools,
                stop_when=stop_when,
                max_output_tokens=max_output_tokens,
                provider_options=provider_options,
                headers=headers,
                max_retries=max_retries,
                request_timeout_s=request_timeout_s,
                on_step_finish=on_step_finish,
                prepare_step=prepare_step,
                sleep=sleep,
                retry_initial_delay_s=retry_initial_delay_s,
                on_attempt_error=on_attempt_error,
            )
    except TimeoutError as exc:
        if not deadline.expired():
            raise  # a timeout of the model call itself, not of the whole turn
        # ``asyncio.timeout`` raises a bare TimeoutError; say which limit it was.
        raise TimeoutError(f"agent turn exceeded {timeout_s}s") from exc
