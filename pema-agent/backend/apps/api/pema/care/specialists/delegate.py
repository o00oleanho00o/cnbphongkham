"""``delegate``: the care agent hands work to a specialist, at depth 1, under a budget (PLAN-AI01-M
sections 9, 11).

New module (not a port). Two parts.

``DelegationService.delegate`` runs ONE delegation, in this order:

1. the specialist exists (``care-scheduler``, ``care-knowledge``, ``care-reviewer``; the short names
   ``scheduler`` / ``knowledge`` / ``reviewer`` are accepted);
2. its kill switch (M3: ``KillSwitchState.blocks``) is off, else ``needs_human`` and an ``actions_log`` row;
3. the turn budget grants a slot (``TurnBudget.reserve``: at most 3 specialists, deadline, token ceiling),
   else
   ``needs_human`` and an ``actions_log`` row ``budget_exhausted:<why>``;
4. a row in ``agent.tasks`` (a child of the turn's own root row: ``parent_id`` is always the root, so the
   tree is
   never deeper than 1; ``TaskStore.create_child`` refuses anything else);
5. the specialist runs with the strictest profile of the chain (``profile_of_turn``), its resolved tools,
   at most
   8 model steps, the tokens left in the turn and the time left until the deadline;
6. the answer is checked against facts (``finalize_*``: citations and slots come from the tools, not from the
   model), the row is finished with tokens, cost and timing, and the ``TaskResult`` is returned.

Whatever goes wrong (a provider error, a timeout, no structured answer, an exhausted step cap) the result is
``TaskResult(needs_human=True)``: the care agent never receives an exception from a specialist and never
has to
read free text to learn that a person must take over. Logs carry ids, the agent id and codes only.

``build_delegate_spec`` is the ``ToolSpec`` of the tool ``delegate``. It is available to every agent EXCEPT
the
specialists (``available``), it is in the deny list of every specialist record, it is never in an
allowlist, and
its handler needs a ``CareTurnScope`` in ``ToolContext.extras``: three independent locks for depth 1. The
wiring
adds it to the registry: ``DefaultToolRegistry(deps, definitions=[*build_tool_definitions(deps), spec])``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.care.autonomy import KillSwitchState, load_kill_switch
from pema.care.budget import BudgetReason
from pema.care.models import ActionDisposition, TaskStatus
from pema.care.ports import CareStore, SpecialistRunner, TaskStore
from pema.care.specialists.knowledge import finalize_knowledge_result
from pema.care.specialists.scheduler import finalize_scheduler_result
from pema.care.specialists.scope import CARE_TURN_EXTRA, CareTurnScope
from pema.care.specialists.spec import (
    DELEGATE_TOOL,
    KNOWLEDGE_ID,
    REVIEWER_ID,
    SCHEDULER_ID,
    SPECIALIST_IDS,
    RunState,
    SpecialistCall,
    SpecialistRun,
    SpecialistSpec,
    profile_of_turn,
)
from pema.care.specialists.toolkit import SpecialistToolkit
from pema.care.task_result import TaskResult, needs_human_result
from pema_contracts.agents import AgentProfile
from pema_contracts.common import JsonObject
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolScope, ToolSpec

logger = logging.getLogger(__name__)

SHORT_NAMES: dict[str, str] = {"scheduler": SCHEDULER_ID, "knowledge": KNOWLEDGE_ID, "reviewer": REVIEWER_ID}

BUDGET_EXHAUSTED = "budget_exhausted"
BLOCKED_KILL_SWITCH = "delegation:blocked_kill_switch"

type Clock = Callable[[], datetime]
type Finalizer = Callable[[TaskResult, RunState], TaskResult]
type RecordLookup = Callable[[str], Any]

DEFAULT_FINALIZERS: dict[str, Finalizer] = {
    KNOWLEDGE_ID: finalize_knowledge_result,
    SCHEDULER_ID: finalize_scheduler_result,
}


class UnknownSpecialistError(LookupError):
    """``agent_name`` is not one of the three specialists."""


class DelegationService:
    def __init__(
        self,
        *,
        specs: Mapping[str, SpecialistSpec],
        runners: Mapping[str, SpecialistRunner],
        toolkit: SpecialistToolkit,
        tasks: TaskStore,
        store: CareStore,
        records: Mapping[str, AgentProfile] | None = None,
        kill_switch: Callable[[], KillSwitchState] = load_kill_switch,
        finalizers: Mapping[str, Finalizer] | None = None,
        price_per_1k_tokens: Decimal = Decimal(0),
        clock: Clock | None = None,
    ) -> None:
        self._specs = dict(specs)
        self._runners = dict(runners)
        self._toolkit = toolkit
        self._tasks = tasks
        self._store = store
        self._records = dict(records or {})
        self._kill_switch = kill_switch
        self._finalizers = dict(DEFAULT_FINALIZERS if finalizers is None else finalizers)
        self._price = price_per_1k_tokens
        self._clock = clock or (lambda: datetime.now(UTC))

    # --------------------------------------------------------------------------------- lookup
    def spec_for(self, agent_name: str) -> SpecialistSpec:
        agent_id = SHORT_NAMES.get(agent_name, agent_name)
        spec = self._specs.get(agent_id)
        if spec is None or agent_id not in SPECIALIST_IDS:
            raise UnknownSpecialistError(agent_name)
        return spec

    # ------------------------------------------------------------------------------ the call
    async def delegate(
        self, scope: CareTurnScope, agent_name: str, task: str, context_ref: str | None
    ) -> TaskResult:
        spec = self.spec_for(agent_name)
        care_agent_id = scope.care_agent.id

        if self._kill_switch().blocks(spec.agent_id):
            await self._audit(care_agent_id, BLOCKED_KILL_SWITCH)
            return needs_human_result("Chuyên viên đang tạm tắt; cần nhân viên xử lý.")

        refused = scope.budget.reserve()
        root_id = await self._root(scope)
        started = self._clock()
        deadline_at = scope.budget.deadline_at
        context = self._context(scope, context_ref)
        child_id = await self._tasks.create_child(
            root_id,
            agent_id=spec.agent_id,
            input={
                "task_chars": len(task),
                "context_ref": context_ref or "",
                "context_keys": sorted(context),
            },
            started_at=started,
            deadline_at=deadline_at,
        )
        if refused is not None:
            return await self._finish_exhausted(care_agent_id, child_id, refused, tokens=0)

        state = RunState()
        profile_key = profile_of_turn(scope.care_agent.profile, [spec])
        tools: Mapping[str, AgentTool] = self._toolkit.build(
            spec, self._records.get(spec.agent_id), profile_key, scope, state
        )
        call = SpecialistCall(
            spec=spec,
            task=task,
            context=context,
            tools=tools,
            state=state,
            max_steps=min(spec.max_steps, scope.budget.max_tool_steps),
            token_budget=scope.budget.tokens_left(),
            seconds_left=scope.budget.seconds_left(),
        )
        try:
            async with asyncio.timeout(call.seconds_left):
                run = await self._runners[spec.agent_id].run(call)
        except TimeoutError:
            return await self._finish_exhausted(care_agent_id, child_id, BudgetReason.DEADLINE, tokens=0)
        except Exception as err:
            logger.error("specialist run failed", extra={"agent": spec.agent_id, "error": type(err).__name__})
            result = needs_human_result("Chuyên viên gặp lỗi; cần nhân viên xử lý.")
            await self._tasks.finish(
                child_id,
                status=TaskStatus.FAILED,
                result=result,
                tokens=0,
                cost=Decimal(0),
                finished_at=self._clock(),
                error=type(err).__name__,
            )
            return result
        return await self._conclude(scope, spec, child_id, run, state)

    # ----------------------------------------------------------------------------- internals
    async def _conclude(
        self, scope: CareTurnScope, spec: SpecialistSpec, child_id: Any, run: SpecialistRun, state: RunState
    ) -> TaskResult:
        scope.budget.charge_tokens(run.tokens)
        if run.result is None:
            reason = (
                BudgetReason.TOOL_STEPS
                if run.stopped_by_steps
                else BudgetReason.TOKENS
                if run.stopped_by_tokens
                else None
            )
            if reason is not None:
                return await self._finish_exhausted(scope.care_agent.id, child_id, reason, tokens=run.tokens)
            result = needs_human_result("Chuyên viên không trả kết quả có cấu trúc; cần nhân viên xử lý.")
            await self._finish(child_id, TaskStatus.NEEDS_HUMAN, result, run.tokens, "no_result")
            return result
        finalizer = self._finalizers.get(spec.agent_id)
        result = finalizer(run.result, state) if finalizer is not None else run.result
        status = TaskStatus.NEEDS_HUMAN if result.needs_human else TaskStatus.DONE
        await self._finish(child_id, status, result, run.tokens, None)
        return result

    async def _finish(
        self, task_id: Any, status: TaskStatus, result: TaskResult, tokens: int, error: str | None
    ) -> None:
        await self._tasks.finish(
            task_id,
            status=status,
            result=result,
            tokens=tokens,
            cost=(self._price * tokens / Decimal(1000)).quantize(Decimal("0.000001")),
            finished_at=self._clock(),
            error=error,
        )

    async def _finish_exhausted(
        self, care_agent_id: Any, child_id: Any, reason: BudgetReason, *, tokens: int
    ) -> TaskResult:
        result = needs_human_result("Hết ngân sách cho lượt này; cần nhân viên xử lý.")
        await self._finish(
            child_id, TaskStatus.NEEDS_HUMAN, result, tokens, f"{BUDGET_EXHAUSTED}:{reason.value}"
        )
        await self._audit(care_agent_id, f"{BUDGET_EXHAUSTED}:{reason.value}")
        return result

    async def _audit(self, care_agent_id: Any, action_type: str) -> None:
        await self._store.record_action(
            care_agent_id,
            action_type=action_type,
            disposition=ActionDisposition.PAUSED.value,
            depth=None,
            at=self._clock(),
        )

    async def _root(self, scope: CareTurnScope) -> Any:
        if scope.root_task_id is None:
            scope.root_task_id = await self._tasks.create_root(
                scope.care_agent.id, started_at=scope.budget.started_at, deadline_at=scope.budget.deadline_at
            )
        return scope.root_task_id

    @staticmethod
    def _context(scope: CareTurnScope, context_ref: str | None) -> JsonObject:
        if not context_ref:
            return {}
        return dict(scope.contexts.get(context_ref, {}))


# ------------------------------------------------------------------------------------- the tool
class DelegateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(
        description=(
            "Chuyên viên cần giao việc: care-scheduler (đặt lịch), care-knowledge (tra kho tri thức), "
            "care-reviewer (rà soát nháp)"
        )
    )
    task: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Việc cần làm, ngắn gọn. Với care-reviewer: chính bản nháp cần rà soát. Không ghi tên hay SĐT."
        ),
    )
    context_ref: str | None = Field(
        default=None,
        max_length=100,
        description="Mã tham chiếu ngữ cảnh do hệ thống cấp cho lượt này (nếu có)",
    )


NOT_A_CARE_TURN = "delegate chỉ dùng được trong lượt chăm sóc khách hàng của agent chăm sóc."


def build_delegate_spec(service: DelegationService) -> ToolSpec:
    """The ``ToolSpec`` of ``delegate`` (care agents only; see the module docstring for the three locks)."""

    def available(scope: ToolScope) -> bool:
        return scope.agent_id not in SPECIALIST_IDS

    def build(ctx: ToolContext) -> AgentTool:
        async def handler(args: DelegateInput) -> object:
            care_scope = ctx.extras.get(CARE_TURN_EXTRA)
            if not isinstance(care_scope, CareTurnScope):
                return ket_qua_loi(NOT_A_CARE_TURN)
            try:
                result = await service.delegate(care_scope, args.agent_name, args.task, args.context_ref)
            except UnknownSpecialistError:
                return ket_qua_loi(
                    "Không có chuyên viên tên này. Chọn care-scheduler, care-knowledge hoặc care-reviewer."
                )
            except Exception as err:
                logger.error("delegation failed", extra={"error": type(err).__name__})
                return ket_qua_loi("Giao việc thất bại. Coi như cần nhân viên xử lý.")
            return result.model_dump(mode="json")

        return FunctionTool(
            name=DELEGATE_TOOL,
            description=(
                "Giao một việc cho chuyên viên (đặt lịch, tra kho tri thức, rà soát nháp). Trả về kết quả có "
                "cấu trúc: needs_human, confidence, citations, artifacts. Chỉ đọc các trường đó; nếu "
                "needs_human=true thì cần nhân viên xử lý."
            ),
            input_model=DelegateInput,
            handler=handler,
        )

    return ToolSpec(
        key=DELEGATE_TOOL,
        label="Giao việc cho chuyên viên",
        description="Care agent giao việc cho chuyên viên (độ sâu 1).",
        group=ToolGroup.ACTION,
        build=build,
        available=available,
        unavailable_hint="Chuyên viên không được giao việc tiếp.",
        counts_as_capability=False,
    )
