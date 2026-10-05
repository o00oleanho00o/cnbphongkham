# ported from: src/agent/tools/schedule-task-tool.ts
"""Tool for the model to set / view / edit / cancel a reminder or an agent-run schedule through the
conversation (section 7, ``thiet-ke-scheduler.md``). The logic of each action lives in
``schedule_task_actions``, the pydantic schemas in ``schedule_task_tool_schema`` - split so this file is only
the ``FunctionTool`` wiring, not mixing "how it is done" into "what this tool is".

THREAD SCOPE is at the STORE LAYER (``SchedulerPort``), not here: every get / delete function of the port
already binds ``(account_id, thread_id)``, so even if the action logic forgot a check the store would still
stop an IDOR.

``runs_in_scheduled_turn=False`` (declared in the tool catalog) - Hermes' rule number 1: a job must not spawn
a job. The catalog also keeps this tool out of ``patient_channel``.

Forced deviations: Vercel AI SDK ``tool()`` -> ``FunctionTool`` (pydantic wire model, a validation error is a
``ket_qua_loi``), zod ``safeParse`` -> ``TypeAdapter.validate_python``, ``catch (err)`` keeps the same
contract: an infrastructure failure of the scheduler port (the original test provoked a real SQLite error by
dropping the table) becomes a ``ket_qua_loi``, never an exception into the agent loop. The failure sentence
carries the exception class name instead of the raw message (see the comment in the ``except`` branch).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from pema.agent.tools.function_tool import FunctionTool
from pema.agent.tools.schedule_task_actions import do_cancel, do_create, do_list, do_update
from pema.agent.tools.schedule_task_tool_description import SCHEDULE_TASK_DESCRIPTION
from pema.agent.tools.schedule_task_tool_schema import (
    CancelScheduleTaskInput,
    CreateScheduleTaskInput,
    ListScheduleTaskInput,
    ScheduleTaskWireInput,
    schedule_task_input_adapter,
)
from pema.agent.tools.tool_deps import ToolDeps
from pema.agent.tools.tool_failure_result import ket_qua_loi
from pema.shared.logger import create_logger
from pema_contracts.tools import ToolContext

log = create_logger("schedule-task")

# Restate the requirement of each action in words, so the missing-parameter sentence is ENOUGH for the model
# to call again correctly the next time instead of guessing. The list of wrong fields comes from the
# validation errors themselves, this part only adds meaning.
YEU_CAU_THEO_ACTION: dict[str, str] = {
    "create": "action='create' cần đủ: name, kind ('message' hoặc 'agent'), payload, schedule.",
    "list": "action='list' không nhận tham số nào khác.",
    "cancel": "action='cancel' cần id - gọi action='list' để lấy id, đừng tự đoán.",
    "update": "action='update' cần id, kèm ít nhất một trong name/payload/schedule.",
}


def _error_fields(error: ValidationError) -> list[str]:
    """Field paths of the validation errors, like ``issues.map(i => i.path.join("."))`` of zod: the first
    location element is the ``action`` tag of the discriminated union (zod has no such element), and an error
    inside the ``schedule`` union is reported at ``schedule`` itself (zod's ``invalid_union`` issue)."""
    paths: list[str] = []
    for item in error.errors(include_input=False, include_url=False):
        loc: Sequence[str | int] = item["loc"][1:]
        if loc and loc[0] == "schedule":
            loc = loc[:1]
        path = ".".join(str(p) for p in loc)
        if path:
            paths.append(path)
    return list(dict.fromkeys(paths))


def cau_thieu_tham_so(action: str, loi: ValidationError) -> str:
    """Compose the missing-parameter sentence. Names the broken field BY NAME: a generic sentence such as
    "invalid parameter" makes the model fumble, and every fumble is one more tool call."""
    truong = _error_fields(loi)
    ke = f"Thiếu hoặc sai tham số: {', '.join(truong)}. " if truong else "Tham số không hợp lệ. "
    return (
        f"{ke}{YEU_CAU_THEO_ACTION[action]} Gọi lại tool với đủ tham số, đừng báo với người dùng là đã xong."
    )


def create_schedule_task_tool(ctx: ToolContext, deps: ToolDeps) -> FunctionTool[ScheduleTaskWireInput]:
    async def handler(wire: ScheduleTaskWireInput) -> object:
        try:
            # The cross-field constraint by action is enforced HERE and not in the schema: a rejecting schema
            # makes the loop build the input error before this line is reached, the model could not read a
            # sentence to fix itself in the same turn.
            raw: dict[str, Any] = wire.model_dump(mode="json", by_alias=True, exclude_none=True)
            try:
                narrowed = schedule_task_input_adapter.validate_python(raw)
            except ValidationError as err:
                # Field locations only, never the offending values (they may be personal data).
                log.warning(
                    "schedule_task thiếu tham số",
                    action=wire.action,
                    fields=_error_fields(err),
                )
                return ket_qua_loi(cau_thieu_tham_so(wire.action, err))

            if isinstance(narrowed, CreateScheduleTaskInput):
                return await do_create(ctx, deps, narrowed)
            if isinstance(narrowed, ListScheduleTaskInput):
                return await do_list(ctx, deps)
            if isinstance(narrowed, CancelScheduleTaskInput):
                return await do_cancel(ctx, deps, narrowed.id)
            return await do_update(ctx, deps, narrowed)
        except Exception as err:
            # Return the message for the model to interpret, do not raise into the agent loop - same rule as
            # web_search / read_image (an infrastructure failure must not kill the whole turn). Forced
            # deviation: the original put the raw ``err.message`` (a SQLite error) into the sentence; a
            # Postgres driver error can carry the query parameters and the failing row (personal data), so the
            # model only gets the exception CLASS name. The full error goes to the log through
            # ``serialize_error_safely``.
            reason = type(err).__name__
            # ``wire.action`` and not the narrowed input: the narrowed input only exists inside the try, and
            # this branch must also catch an error raised BEFORE the type was narrowed.
            log.error("Tool schedule_task lỗi", err=err, action=wire.action)
            return ket_qua_loi(
                f"Thao tác lịch hẹn thất bại ({reason}). Nói thật với người dùng, đừng coi như đã làm xong."
            )

    # FLAT shape going out to the provider (full reason in ``schedule_task_tool_schema``) - a union at the
    # root
    # node made DeepSeek refuse the whole request, so the bot was mute on every message, not only on a
    # turn that
    # touches schedules.
    return FunctionTool(
        name="schedule_task",
        description=SCHEDULE_TASK_DESCRIPTION,
        input_model=ScheduleTaskWireInput,
        handler=handler,
    )
