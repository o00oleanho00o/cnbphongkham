# ported from: src/agent/tools/schedule-task-tool-schema.ts
"""Schemas of the ``schedule_task`` tool: the WIRE shape sent to the provider and the real contract that
``execute`` parses again.

Forced deviation (zod -> pydantic):

* the 4 schedule shapes are SUBCLASSES of the contract inputs of ``pema_contracts.scheduler``
(``OnceAtInput``,
  ``OnceInMinutesInput``, ``EveryInput``, ``CronInput``), so an instance can be handed to
  ``ScheduleParser.parse_schedule`` as is ("the shape matches ``ScheduleInput`` 1-1 to pass straight through,
  no conversion"). The subclasses only add what the contract does not carry: the model-facing
  descriptions, the
  ``525600`` ceilings, the required ``kind`` and the original camelCase wire name ``inMinutes`` (alias), which
  keeps the production-proven JSON the model was tuned on;
* zod strips unknown keys of the contract objects; pydantic does it with ``extra="ignore"`` on the three
  contract models of the ``action`` union. The flat wire model and the schedule shapes keep ``extra="forbid"``
  (``additionalProperties: false``, the shape zod emitted for the provider) - a stray key now comes back
  to the
  model as a ``ket_qua_loi`` from ``FunctionTool`` instead of being silently dropped.

Unchanged from the original (see the long comments there): the schedule is a plain UNION on ``kind`` (NOT a
discriminated union: ``once`` has two shapes that share the discriminant), and the WIRE shape is a FLAT
object.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from pema_contracts.scheduler import (
    CronInput,
    EveryInput,
    OnceAtInput,
    OnceInMinutesInput,
    ScheduleKind,
)


class OnceAtScheduleInput(OnceAtInput):
    kind: Literal[ScheduleKind.ONCE] = Field(...)
    date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description='Ngày dạng YYYY-MM-DD theo giờ Việt Nam, vd "2026-08-01"',
    )
    time: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description='Giờ dạng HH:mm (24h) theo giờ Việt Nam, vd "15:00"',
    )


class OnceInMinutesScheduleInput(OnceInMinutesInput):
    kind: Literal[ScheduleKind.ONCE] = Field(...)
    # Ceiling 525600 (1 year) - without it ``now + in_minutes * 60`` in the schedule parser overflows the
    # datetime range when it exceeds the bound; the tool has a try/except but the POST /api/schedule route
    # (which
    # shares this schema) does not, so the error would leak as a 500 instead of a 400 with a clear reason.
    in_minutes: int = Field(
        alias="inMinutes",
        ge=1,
        le=525600,
        description="Số phút kể từ bây giờ, vd 30 = 30 phút nữa",
    )


class EveryScheduleInput(EveryInput):
    kind: Literal[ScheduleKind.EVERY] = Field(...)
    # Same 525600 (1 year) ceiling as ``in_minutes`` above - the same breaking path: ``compute_next_run`` adds
    # ``steps * interval`` to a datetime and overflows its bounds.
    minutes: int = Field(ge=1, le=525600, description="Lặp lại mỗi bấy nhiêu phút")


class CronScheduleInput(CronInput):
    kind: Literal[ScheduleKind.CRON] = Field(...)
    expr: str = Field(
        min_length=1,
        max_length=120,
        description='Biểu thức cron 5 trường theo giờ Việt Nam, vd "0 7 * * *" = 7h sáng mỗi ngày',
    )


type ScheduleInputTool = (
    OnceAtScheduleInput | OnceInMinutesScheduleInput | EveryScheduleInput | CronScheduleInput
)
"""Exactly 1 of 4 shapes: ``once`` at an absolute moment (date+time), ``once`` relative (inMinutes), ``every``
repeating by minutes, or ``cron`` by expression - all four read in Vietnam time. Each is a
``ScheduleInput``."""

SCHEDULE_UNION_DESCRIPTION = (
    "Đúng 1 trong 4 dạng: once theo mốc giờ tuyệt đối (date+time), once tương đối (inMinutes), "
    "every lặp theo phút, hoặc cron theo biểu thức cron - cả 4 đều hiểu theo giờ Việt Nam."
)

MAX_NAME_CHARS = 100
"""Display label on the dashboard / action list - not the content sent. Exported so the dashboard API
reuses exactly this threshold instead of declaring a second number that drifts."""

MAX_PAYLOAD_CHARS = 4000
"""Payload ceiling - a self-chosen POLICY (not a Zalo limit), wide enough for a long reminder and a detailed
agent prompt. Same size as ``MAX_PROMPT_CHARS`` of ``create-image-tool`` for consistency in the catalog."""


class CreateScheduleTaskInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["create"]
    name: str = Field(
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description="Nhãn ngắn để nhận ra lịch này trong action='list'",
    )
    kind: Literal["message", "agent"] = Field(
        description=(
            "'message' = gửi nguyên văn payload lúc tới giờ, không tốn lượt LLM. "
            "'agent' = chạy 1 lượt agent có tool với payload là prompt."
        ),
    )
    payload: str = Field(
        min_length=1,
        max_length=MAX_PAYLOAD_CHARS,
        description=(
            "Nội dung gửi (kind='message') hoặc prompt cho lượt agent (kind='agent') - "
            "phải TỰ CHỨA đủ ngữ cảnh"
        ),
    )
    schedule: ScheduleInputTool = Field(description=SCHEDULE_UNION_DESCRIPTION)


class ListScheduleTaskInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["list"]


class CancelScheduleTaskInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["cancel"]
    id: str = Field(min_length=1, description="id lấy từ action='list' - TUYỆT ĐỐI không tự đoán")


class UpdateScheduleTaskInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["update"]
    id: str = Field(min_length=1, description="id lấy từ action='list' - TUYỆT ĐỐI không tự đoán")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description="Bỏ trống = giữ nguyên tên cũ",
    )
    payload: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PAYLOAD_CHARS,
        description="Bỏ trống = giữ nguyên nội dung cũ",
    )
    schedule: ScheduleInputTool | None = Field(default=None, description="Bỏ trống = giữ nguyên lịch cũ")


type ScheduleTaskInput = Annotated[
    CreateScheduleTaskInput | ListScheduleTaskInput | CancelScheduleTaskInput | UpdateScheduleTaskInput,
    Field(discriminator="action"),
]
"""THE REAL CONTRACT of the tool - a strict union on ``action``. No longer what is sent to the provider (see
``ScheduleTaskWireInput`` below), but what ``execute`` parses again to narrow the type. Every type derived
from here is unchanged, so ``schedule_task_actions`` does not have to know about the wire shape."""

schedule_task_input_adapter: TypeAdapter[ScheduleTaskInput] = TypeAdapter(ScheduleTaskInput)


class ScheduleTaskWireInput(BaseModel):
    """The shape that GOES OUT TO THE PROVIDER. Flat: ``action`` is an enum, every other field is optional
    because which field is required depends on ``action``.

    Why not send ``ScheduleTaskInput`` directly: a union at the ROOT node translates into
    ``{"$schema": ..., "oneOf": [...]}`` - no ``type`` key. DeepSeek checks ``parameters.type`` must equal
    ``"object"`` and refuses the WHOLE REQUEST::

        400 Invalid schema for function 'schedule_task':
            schema must be a JSON Schema of 'type: "object"', got 'type: null'.

    Since the tool set travels with EVERY turn, the consequence is that the bot is completely MUTE with
    DeepSeek,
    not just on a turn that touches schedules (real log: ``steps: 0``).

    Measured on the real api.deepseek.com (deepseek-v4-flash, 07/08/2026): all 13 tools as before -> 400; this
    tool alone -> 400; this tool in the flat shape -> 200, even with the other 12 tools attached. Going around
    through 9router does NOT save it.

    The constraint applies only to the ROOT node: a union NESTED inside an object is accepted by every
    provider -
    ``schedule`` right below, ``documentBlockSchema``, ``spreadsheetCellSchema`` are all like that and all
    passed
    in the same measurement.

    The cross-field constraint ("create must have name/kind/payload/schedule") is not lost, it MOVES to
    ``execute``. Deliberately NO model-level validator here: a schema that rejects makes the loop build
    the input
    error BEFORE ``execute`` runs, losing the road to return a ``ket_qua_loi`` the model reads and retries in
    the same turn.

    The description of each field must carry the information that ``required`` no longer states. Measured 4
    request shapes x 2 times on DeepSeek: 8/8 times the model filled all fields and passed the strict union;
    in the "cancel schedule X" case the model even called ``list`` first to get the id.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "list", "cancel", "update"] = Field(
        description=(
            "create = đặt lịch mới (cần name, kind, payload, schedule). "
            "list = xem lịch đang có, không cần tham số nào khác. "
            "cancel = hủy (cần id). update = sửa (cần id, kèm trường muốn đổi)."
        ),
    )
    id: str | None = Field(
        default=None,
        min_length=1,
        description="BẮT BUỘC với cancel/update. Lấy từ action='list' - TUYỆT ĐỐI không tự đoán.",
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description=(
            "BẮT BUỘC với create. Nhãn ngắn để nhận ra lịch này trong action='list'. "
            "Với update: bỏ trống = giữ tên cũ."
        ),
    )
    kind: Literal["message", "agent"] | None = Field(
        default=None,
        description=(
            "BẮT BUỘC với create. 'message' = gửi nguyên văn payload lúc tới giờ, không tốn lượt LLM. "
            "'agent' = chạy 1 lượt agent có tool với payload là prompt. Không đổi được sau khi tạo."
        ),
    )
    payload: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PAYLOAD_CHARS,
        description=(
            "BẮT BUỘC với create. Nội dung gửi (kind='message') hoặc prompt cho lượt agent (kind='agent') - "
            "phải TỰ CHỨA đủ ngữ cảnh. Với update: bỏ trống = giữ nội dung cũ."
        ),
    )
    # Repeat the whole 4-shapes sentence: this description OVERRIDES the original one of the schedule union in
    # the emitted JSON Schema; a truncated one makes the model lose the only part telling it which 4 shapes
    # exist.
    schedule: ScheduleInputTool | None = Field(
        default=None,
        description=(
            "BẮT BUỘC với create. Với update: bỏ trống = giữ lịch cũ. Đúng 1 trong 4 dạng: once theo mốc giờ "
            "tuyệt đối (date+time), once tương đối (inMinutes), every lặp theo phút, hoặc cron theo biểu "
            "thức cron - cả 4 đều hiểu theo giờ Việt Nam."
        ),
    )
