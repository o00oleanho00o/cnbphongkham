"""The model-backed runner of a specialist (recipe M4 steps 2 and 6).

New module (not a port). It uses the project's own tool loop (``pema.agent.stream_text_result.chay_stream``),
the same one every agent turn uses, with:

* the tools of the specialist (already resolved from its allowlist) plus ``submit_result``: the
  schema-constrained final answer, whose argument schema IS ``TaskResult``. The care agent reads the fields of
  that object, never the free text of the model;
* ``stop_when``: the step cap of the budget (8), the end of the run once ``submit_result`` was called, and the
  token ceiling of what is left of the turn;
* a fallback for a model that ends with plain text: if the text parses as a ``TaskResult`` JSON object it is
  accepted, otherwise the run has NO result and the delegation becomes ``needs_human`` (nothing is guessed
  from
  prose).

The run never raises for a model problem: a provider error is the caller's ``failed`` task, see
``delegate.DelegationService``. ``tool_output_text_filter`` is the PII mask of ``patient_channel`` over what a
tool returns to the model (the wiring passes ``pema.policy`` 's masker; ``None`` in tests).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from pema.agent.model_types import ChatModel, ModelMessage, ModelUsage, RawStep
from pema.agent.stream_text_result import StopCondition, chay_stream, step_count_is
from pema.agent.tools.function_tool import FunctionTool
from pema.care.specialists.spec import SUBMIT_RESULT_TOOL, SpecialistCall, SpecialistRun
from pema.care.task_result import TaskResult, task_result_schema
from pema_contracts.tools import AgentTool

GENERAL_RULES = (
    "\n\nQuy tắc chung: chỉ làm đúng nhiệm vụ được giao, chỉ dùng tool bạn có. Không chẩn đoán, không kê "
    "đơn. "
    "Không ghi tên, số điện thoại hay địa chỉ của ai vào kết quả. Khi xong BẮT BUỘC gọi submit_result "
    "đúng một "
    "lần (summary ngắn, artifacts có cấu trúc, confidence từ 0 đến 1). Nếu không làm được, gọi "
    "submit_result với "
    "needs_human=true."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _used_tokens(usage: ModelUsage) -> int:
    if usage.total_tokens is not None:
        return usage.total_tokens
    return (usage.input_tokens or 0) + (usage.output_tokens or 0)


def parse_result_text(text: str) -> TaskResult | None:
    """A ``TaskResult`` from the plain text of a model that did not call ``submit_result``; ``None`` if "
    "it is not one."""
    candidate = _FENCE.sub("", text.strip())
    if not candidate.startswith("{"):
        return None
    try:
        return TaskResult.model_validate(json.loads(candidate))
    except (ValueError, ValidationError):
        return None


@dataclass
class _Holder:
    result: TaskResult | None = None


def _total_tokens(steps: Sequence[RawStep]) -> int:
    return sum(_used_tokens(step.usage) for step in steps if step.usage is not None)


class LlmSpecialistRunner:
    """``SpecialistRunner`` over a ``ChatModel`` (the shared provider adapters of D1)."""

    def __init__(
        self,
        model: ChatModel,
        *,
        tool_output_text_filter: Callable[[str], str] | None = None,
        max_retries: int = 1,
        max_output_tokens: int | None = None,
    ) -> None:
        self._model = model
        self._filter = tool_output_text_filter
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens

    async def run(self, call: SpecialistCall) -> SpecialistRun:
        holder = _Holder()

        async def submit(args: TaskResult) -> object:
            holder.result = args
            return "Đã nhận kết quả."

        submit_tool = FunctionTool(
            name=SUBMIT_RESULT_TOOL,
            description="Nộp kết quả cuối cùng của nhiệm vụ. Gọi đúng một lần khi xong.",
            input_model=TaskResult,
            handler=submit,
            parameters=task_result_schema(),
        )
        tools: dict[str, AgentTool] = {**call.tools, SUBMIT_RESULT_TOOL: submit_tool}
        stop_when: list[StopCondition] = [
            step_count_is(call.max_steps),
            lambda _steps: holder.result is not None,
            lambda steps: _total_tokens(steps) >= call.token_budget,
        ]
        context = json.dumps(call.context, ensure_ascii=False, default=str)
        user_text = f"Nhiệm vụ: {call.task}\nNgữ cảnh (đã che thông tin cá nhân): {context}"
        messages: list[ModelMessage] = [{"role": "user", "content": user_text}]
        outcome = await chay_stream(
            model=self._model,
            system=call.spec.persona + GENERAL_RULES,
            messages=messages,
            tools=tools,
            stop_when=stop_when,
            max_output_tokens=self._max_output_tokens,
            max_retries=self._max_retries,
            tool_output_text_filter=self._filter,
        )
        tokens = _used_tokens(outcome.total_usage)
        steps = len(outcome.steps)
        result = holder.result
        if result is None:
            result = parse_result_text(outcome.text)
        last: Any = outcome.steps[-1] if outcome.steps else None
        cut = result is None and last is not None and bool(last.tool_calls)
        return SpecialistRun(
            result=result,
            tokens=tokens,
            steps=steps,
            stopped_by_steps=cut and steps >= call.max_steps,
            stopped_by_tokens=cut and tokens >= call.token_budget,
        )
