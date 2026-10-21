"""The ``crm`` plugin: what the clinic's agent may do in the CRM for the person it chats with
(docs/PLAN-crm-plugin.md 3.3).

Seven tools over the CRM's agent gateway, reached through ``crm-signer`` (``client.py``). The person is the
chat's own ``channel`` and ``user_id`` from ``ToolContext``, set by the code that received the message; no
tool takes a person, a phone lookup or a patient id from the model, so the model can only act for the person
in front of it. A turn without a person (the CLI, the web test console) is refused. Writes carry an
``Idempotency-Key`` made from the session and the call, so a retried call never books twice.

The tools are the "employee's tools" of the owner's loop frame (docs/IDEAS-agent-loops.md 5). The plugin also
takes the CRM's events (``events.py``, ``POST /v1/hooks/crm/events``) into its own tables (``store.py``): the
trigger side of the reminder loop, whose acting side is step 6.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

from agent_app.plugins import PluginContext
from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec
from plugins.sso.keys import KeySet

from .client import CrmClient, CrmError
from .events import EventVerifier, events_router
from .reminders import ReminderPolicy, Reminders
from .store import MemoryReminderStore, PostgresReminderStore, ReminderStore

CHANNEL: Final = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
EXTERNAL_ID: Final = re.compile(r"[A-Za-z0-9_.:@=-]{1,128}")
NO_PERSON: Final = (
    "Chỉ đặt lịch được trong cuộc chat với khách (Zalo). Ở đây hãy hướng dẫn khách nhắn qua Zalo của phòng "
    "khám hoặc gọi hotline."
)
IN_GROUP: Final = (
    "Trong nhóm chat không xem, đặt hay đổi lịch được vì cả nhóm đọc được. Mời khách nhắn riêng cho phòng "
    "khám."
)
STATUS: Final = {
    "booked": "đã đặt, chưa xác nhận",
    "confirmed": "đã xác nhận",
    "arrived": "đã đến",
    "in_progress": "đang khám",
    "completed": "đã khám xong",
    "cancelled": "đã hủy",
    "missed": "khách không đến",
}


class NoArgs(BaseModel):
    pass


class FreeSlotsArgs(BaseModel):
    day_from: date = Field(description="Ngày đầu tiên cần xem (YYYY-MM-DD).")
    days: int = Field(default=1, ge=1, le=14, description="Số ngày cần xem, tính từ day_from (1-14).")
    duration_min: int = Field(default=30, ge=5, le=480, description="Thời lượng buổi hẹn, phút.")


class SaveContactArgs(BaseModel):
    full_name: str = Field(min_length=1, max_length=120, description="Họ tên khách tự nói.")
    phone: str = Field(min_length=1, max_length=32, description="Số điện thoại khách tự nói.")
    messages_consent: bool | None = Field(
        default=None,
        description="Khách đồng ý (true) hay không (false) nhận tin nhắc lịch qua Zalo; chưa hỏi: để trống.",
    )


class BookArgs(BaseModel):
    starts_at: datetime = Field(description="Giờ bắt đầu, ISO 8601, ví dụ 2026-10-22T09:30+07:00.")
    duration_min: int = Field(default=30, ge=5, le=480, description="Thời lượng, phút.")
    note: str | None = Field(default=None, max_length=500, description="Dịch vụ khách muốn làm.")


class AppointmentArgs(BaseModel):
    appointment_id: UUID = Field(description="Mã lịch, lấy từ crm_my_appointments.")


class RescheduleArgs(AppointmentArgs):
    starts_at: datetime = Field(description="Giờ mới, ISO 8601, ví dụ 2026-10-22T14:00+07:00.")
    duration_min: int | None = Field(default=None, ge=5, le=480, description="Thời lượng mới; trống là giữ.")


class CancelArgs(AppointmentArgs):
    reason: str = Field(min_length=1, max_length=200, description="Lý do khách nói, ngắn gọn.")


Handler = Callable[[Any, ToolContext], Awaitable[ToolOutput]]


class CrmTools:
    def __init__(
        self, ctx: PluginContext, client: CrmClient, zone: ZoneInfo, store: ReminderStore | None = None
    ) -> None:
        self._ctx = ctx
        self._client = client
        self._zone = zone
        self._store = store

    def _person(self, tool: ToolContext) -> str | None:
        """``/contacts/{channel}/{user}`` of the chat; None when the turn has no person of a chat channel."""
        channel, user = tool.channel, tool.user_id
        if not channel or not user or self._ctx.channel_plugin(channel) is None:
            return None
        if not CHANNEL.fullmatch(channel) or not EXTERNAL_ID.fullmatch(user):
            return None
        return f"/contacts/{channel}/{user}"

    def _at(self, value: datetime) -> str:
        return (value if value.tzinfo else value.replace(tzinfo=self._zone)).isoformat()

    def _local(self, iso: str) -> datetime:
        return datetime.fromisoformat(iso).astimezone(self._zone)

    def _visit(self, row: dict[str, Any]) -> str:
        at = self._local(str(row["starts_at"]))
        status = STATUS.get(str(row["status"]), str(row["status"]))
        return f"- mã {row['id']}: {at:%d/%m/%Y %H:%M}, {row['duration_min']} phút, {status}"

    @staticmethod
    def _key(tool: ToolContext, name: str, *parts: object) -> str:
        """The same call retried within one turn shares a key; the same time asked again in a later turn
        (booked, cancelled, booked again) does not."""
        raw = "\x00".join([tool.session_id, str(tool.now), name, *(str(p) for p in parts)])
        return hashlib.sha256(raw.encode()).hexdigest()[:40]

    def _guarded(self, run: Callable[[Any, ToolContext, str], Awaitable[str]]) -> Handler:
        async def handler(args: Any, tool: ToolContext) -> ToolOutput:
            if tool.is_group:
                return ToolOutput(text=IN_GROUP, is_error=True)
            person = self._person(tool)
            if person is None:
                return ToolOutput(text=NO_PERSON, is_error=True)
            if self._store is not None and tool.conversation_id and tool.channel and tool.user_id:
                # the one-to-one chat a reminder will go to (step 6); a group never gets this far
                await self._store.remember_chat(tool.channel, tool.user_id, tool.conversation_id)
            try:
                return ToolOutput(text=await run(args, tool, person))
            except CrmError as err:
                return ToolOutput(text=str(err), is_error=True)

        return handler

    async def free_slots(self, args: FreeSlotsArgs, tool: ToolContext, _person: str) -> str:
        found = await self._client.call(
            "GET",
            "/free-slots",
            params={
                "day_from": args.day_from.isoformat(),
                "days": args.days,
                "duration_min": args.duration_min,
            },
        )
        lines = [
            f"{day['day']}: " + (", ".join(f"{self._local(s):%H:%M}" for s in day["starts"]) or "hết chỗ")
            for day in found["days"]
        ]
        return f"Giờ còn trống (buổi {found['duration_min']} phút):\n" + "\n".join(lines)

    async def save_contact(self, args: SaveContactArgs, tool: ToolContext, person: str) -> str:
        saved = await self._client.call("PUT", person, body=args.model_dump())
        what = "Đã lưu hồ sơ mới cho khách." if saved["created"] else "Khách đã có hồ sơ; hồ sơ giữ nguyên."
        consent = {True: "đồng ý", False: "không đồng ý", None: "chưa hỏi"}[saved["messages_consent"]]
        return f"{what} Nhận tin nhắc lịch: {consent}."

    async def book(self, args: BookArgs, tool: ToolContext, person: str) -> str:
        starts = self._at(args.starts_at)
        row = await self._client.call(
            "POST",
            f"{person}/appointments",
            body={"starts_at": starts, "duration_min": args.duration_min, "note": args.note},
            idempotency_key=self._key(tool, "book", starts, args.duration_min),
        )
        return "Đã đặt lịch:\n" + self._visit(row)

    async def my_appointments(self, _args: NoArgs, tool: ToolContext, person: str) -> str:
        rows = await self._client.call("GET", f"{person}/appointments")
        if not rows:
            return "Khách chưa có lịch hẹn sắp tới."
        return "Lịch hẹn sắp tới của khách:\n" + "\n".join(self._visit(r) for r in rows)

    async def confirm(self, args: AppointmentArgs, tool: ToolContext, person: str) -> str:
        row = await self._client.call("POST", f"{person}/appointments/{args.appointment_id}/confirm")
        return "Đã xác nhận lịch:\n" + self._visit(row)

    async def reschedule(self, args: RescheduleArgs, tool: ToolContext, person: str) -> str:
        starts = self._at(args.starts_at)
        row = await self._client.call(
            "POST",
            f"{person}/appointments/{args.appointment_id}/reschedule",
            body={"starts_at": starts, "duration_min": args.duration_min},
            idempotency_key=self._key(tool, "reschedule", args.appointment_id, starts),
        )
        return "Đã dời lịch:\n" + self._visit(row)

    async def cancel(self, args: CancelArgs, tool: ToolContext, person: str) -> str:
        row = await self._client.call(
            "POST", f"{person}/appointments/{args.appointment_id}/cancel", body={"reason": args.reason}
        )
        return "Đã hủy lịch:\n" + self._visit(row)

    def specs(self) -> list[ToolSpec[Any]]:
        g = self._guarded
        return [
            ToolSpec(
                name="crm_free_slots",
                description="Xem giờ còn trống của phòng khám trong vài ngày tới, để gợi ý giờ cho khách.",
                args_model=FreeSlotsArgs,
                handler=g(self.free_slots),
                read_only=True,
            ),
            ToolSpec(
                name="crm_save_contact",
                description=(
                    "Lưu họ tên, số điện thoại của khách đang chat (sau khi khách đồng ý cho lưu) và việc "
                    "khách có muốn nhận tin nhắc lịch không. Cần làm trước lần đặt lịch đầu tiên."
                ),
                args_model=SaveContactArgs,
                handler=g(self.save_contact),
            ),
            ToolSpec(
                name="crm_book_appointment",
                description=(
                    "Đặt lịch cho khách đang chat, sau khi khách đã chọn và đồng ý đúng ngày giờ. Giờ phải "
                    "là giờ còn trống từ crm_free_slots."
                ),
                args_model=BookArgs,
                handler=g(self.book),
            ),
            ToolSpec(
                name="crm_my_appointments",
                description="Xem các lịch hẹn sắp tới của khách đang chat, kèm mã lịch.",
                args_model=NoArgs,
                handler=g(self.my_appointments),
                read_only=True,
            ),
            ToolSpec(
                name="crm_confirm_appointment",
                description="Xác nhận một lịch của khách đang chat khi khách nói rõ sẽ đến.",
                args_model=AppointmentArgs,
                handler=g(self.confirm),
            ),
            ToolSpec(
                name="crm_reschedule_appointment",
                description="Dời một lịch của khách đang chat sang giờ mới khách đã đồng ý (giờ còn trống).",
                args_model=RescheduleArgs,
                handler=g(self.reschedule),
            ),
            ToolSpec(
                name="crm_cancel_appointment",
                description="Hủy một lịch của khách đang chat khi khách nói rõ muốn hủy.",
                args_model=CancelArgs,
                handler=g(self.cancel),
            ),
        ]


def register(ctx: PluginContext) -> None:
    base_url = str(ctx.config.get("base_url") or "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must be an http:// or https:// URL")
    timeout_s = max(1, min(30, int(ctx.config.get("timeout_s", 8))))
    # ``transport`` is not a manifest setting: tests hand in an httpx transport faking crm-signer
    transport = ctx.config.get("transport")
    client = CrmClient(
        base_url,
        timeout_s=timeout_s,
        transport=transport if isinstance(transport, httpx.AsyncBaseTransport) else None,
    )
    zone = ZoneInfo(str(ctx.config.get("timezone") or "Asia/Ho_Chi_Minh"))
    store = reminder_store(ctx)
    for spec in CrmTools(ctx, client, zone, store).specs():
        ctx.register_tool(spec)

    jwks_url = str(ctx.config.get("events_jwks_url") or "").strip()
    if not jwks_url.startswith(("http://", "https://")):
        raise ValueError("events_jwks_url must be an http:// or https:// URL")
    keys_transport = ctx.config.get("keys_transport")  # tests: a fake JWKS of the CRM
    keys = KeySet(
        jwks_url,
        transport=keys_transport if isinstance(keys_transport, httpx.AsyncBaseTransport) else None,
    )
    verifier = EventVerifier(keys)
    if ctx.config.get("reminders_enabled") is not True:
        ctx.register_routes(events_router(verifier, store), kind="hooks")
        return
    reminders = Reminders(store, lambda: ctx.proactive, ReminderPolicy.of(ctx.config, zone), client)
    ctx.register_job("reminders", reminders.run)
    ctx.register_routes(events_router(verifier, store, reminders.wake), kind="hooks")


def reminder_store(ctx: PluginContext) -> ReminderStore:
    database = ctx.database
    if database is None:
        return MemoryReminderStore()
    return PostgresReminderStore(database.engine, tenant_id=database.tenant_id, agent=database.agent)
