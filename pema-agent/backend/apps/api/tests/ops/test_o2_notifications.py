"""The notification payload and the outbox rules (package O, step O2). New tests (no zalo-agent original).

No database: the payload serializer (PII-free by construction and by check), the recipients of every kind of
change, the short code and the deep link, the fake delivery of the seam, the new permissions in the matrix, the
``thread_locked`` code and the pure part of the Inbox presence (the holder is not a viewer).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from pema.api.live_access import with_viewers
from pema.clinic.actions.notifications import (
    FakeNotificationDelivery,
    NotificationDelivery,
    NotificationResult,
    OutboxNotification,
    UnsafeNotificationPayloadError,
    deep_link,
    recipients_of,
    serialize_payload,
    short_code,
    summary_of,
)
from pema.clinic.rbac import ASSIGNABLE_ROLES, ROLE_PERMISSIONS
from pema.live.presence import PresenceEntry
from pema_contracts.actions import ActionContext
from pema_contracts.conversations import ConversationSummary
from pema_contracts.errors import ERROR_HTTP_STATUS, ErrorCode
from pema_contracts.live import LiveEventType, PresenceState
from pema_contracts.ops import (
    AssignmentKind,
    NotificationPayload,
    NotificationRecipientKind,
    TakeoverRequest,
)
from pema_contracts.roles import ActorType, Permission, Role

CONVERSATION = UUID("a1b2c3d4-0000-4000-8000-000000000001")
OLD, NEW = UUID(int=11), UUID(int=22)


def payload(**changes: Any) -> NotificationPayload:
    base: dict[str, Any] = {
        "event": AssignmentKind.TAKEOVER,
        "short_code": short_code(CONVERSATION),
        "identity_label": "Long",
        "summary": summary_of(AssignmentKind.TAKEOVER, CONVERSATION),
        "deep_link": deep_link(CONVERSATION),
        "from_user_id": OLD,
        "to_user_id": NEW,
    }
    return NotificationPayload.model_validate({**base, **changes})


# --------------------------------------------------------------------------------- the payload
def test_the_short_code_and_the_deep_link_come_from_the_conversation_id() -> None:
    assert short_code(CONVERSATION) == "#A1B2"
    assert deep_link(CONVERSATION) == f"/inbox?conversation={CONVERSATION}"


def test_a_clean_payload_serializes_to_the_fixed_set_of_keys() -> None:
    data = serialize_payload(payload(), forbidden_names=["Nguyễn Thị Hoa", "Khách mẫu"])
    assert set(data) == {
        "event",
        "short_code",
        "identity_label",
        "urgency",
        "summary",
        "deep_link",
        "from_user_id",
        "to_user_id",
    }
    assert data["event"] == "takeover"
    assert data["short_code"] == "#A1B2"
    assert data["urgency"] == "normal"
    assert data["from_user_id"] == str(OLD)


def test_the_payload_has_no_field_for_a_message_or_a_name() -> None:
    for extra in ({"text": "xin chào"}, {"patient_name": "Hoa"}, {"phone": "0901234567"}):
        with pytest.raises(ValidationError):
            NotificationPayload.model_validate({**payload().model_dump(), **extra})


def test_a_phone_number_in_the_summary_is_refused() -> None:
    for text in ("Gọi lại 0901234567 giúp", "Liên hệ +84 901 234 567", "sđt 090 123 4567"):
        with pytest.raises(UnsafeNotificationPayloadError) as err:
            serialize_payload(payload(summary=text))
        assert "0901" not in str(err.value), "the error never repeats the offending text"


def test_a_phone_number_or_an_email_in_the_identity_label_is_refused() -> None:
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(payload(identity_label="Long 0901234567"))
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(payload(identity_label="long@example.com"))


def test_the_name_of_the_patient_or_of_the_customer_is_refused() -> None:
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(payload(summary="Bà Nguyễn Thị Hoa đang chờ"), forbidden_names=["Nguyễn Thị Hoa"])
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(payload(summary="Khách mẫu hỏi giá"), forbidden_names=["Khách mẫu"])
    # the same words are fine when they are not the name of the thread's people
    serialize_payload(
        payload(summary="Hội thoại #A1B2 đã được tiếp quản"), forbidden_names=["Nguyễn Thị Hoa"]
    )


def test_the_summary_templates_are_clean_for_every_kind() -> None:
    for kind in AssignmentKind:
        for to_agent in (False, True):
            text = summary_of(kind, CONVERSATION, to_agent=to_agent)
            assert "#A1B2" in text
            serialize_payload(payload(event=kind, summary=text))


def test_the_short_code_and_the_deep_link_are_checked_by_the_model() -> None:
    with pytest.raises(ValidationError):
        payload(short_code="A1B2")
    with pytest.raises(ValidationError):
        payload(deep_link="https://example.com/inbox")
    with pytest.raises(ValidationError):
        payload(summary="")


# ------------------------------------------------------------------------------------- recipients
def test_takeover_and_shift_end_tell_the_previous_the_new_and_the_group() -> None:
    for kind in (AssignmentKind.TAKEOVER, AssignmentKind.SHIFT_END, AssignmentKind.ASSIGN):
        rows = recipients_of(kind, previous_user_id=OLD, new_user_id=NEW)
        assert rows == [
            (NotificationRecipientKind.USER, OLD),
            (NotificationRecipientKind.USER, NEW),
            (NotificationRecipientKind.TEAM_GROUP, None),
        ]


def test_a_shift_end_with_nobody_on_duty_tells_the_previous_and_the_group_only() -> None:
    rows = recipients_of(AssignmentKind.SHIFT_END, previous_user_id=OLD, new_user_id=None)
    assert rows == [(NotificationRecipientKind.USER, OLD), (NotificationRecipientKind.TEAM_GROUP, None)]


def test_claim_and_release_tell_the_group_only() -> None:
    for kind in (AssignmentKind.CLAIM, AssignmentKind.RELEASE):
        assert recipients_of(kind, previous_user_id=OLD, new_user_id=NEW) == [
            (NotificationRecipientKind.TEAM_GROUP, None)
        ]


def test_one_person_is_told_once() -> None:
    rows = recipients_of(AssignmentKind.ASSIGN, previous_user_id=OLD, new_user_id=OLD)
    assert rows == [(NotificationRecipientKind.USER, OLD), (NotificationRecipientKind.TEAM_GROUP, None)]


# --------------------------------------------------------------------------------- the seam
async def test_the_fake_delivery_records_and_can_fail() -> None:
    fake = FakeNotificationDelivery()
    assert isinstance(fake, NotificationDelivery)
    ctx = ActionContext(clinic_id=UUID(int=1), actor_type=ActorType.SYSTEM)
    note = OutboxNotification(
        id=uuid4(),
        kind="assignment.takeover",
        recipient_kind=NotificationRecipientKind.USER,
        recipient_user_id=OLD,
        conversation_id=CONVERSATION,
        payload={"short_code": "#A1B2"},
    )
    assert (await fake.deliver(ctx, note)).delivered
    assert fake.sent == [note]
    fake.result = NotificationResult(delivered=False, error_code="unreachable")
    assert (await fake.deliver(ctx, note)).error_code == "unreachable"
    fake.raises = RuntimeError("down")
    with pytest.raises(RuntimeError):
        await fake.deliver(ctx, note)


# ----------------------------------------------------------------- permissions and error code
def test_the_thread_permissions_follow_the_plan() -> None:
    held = {role: ROLE_PERMISSIONS[role] for role in Role}
    for role in ASSIGNABLE_ROLES:
        assert Permission.THREAD_CLAIM in held[role], f"{role} may claim"
    for role in (Role.OWNER, Role.MANAGER):
        assert Permission.THREAD_ASSIGN in held[role]
        assert Permission.THREAD_END_SHIFT in held[role]
    for role in (Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT):
        assert Permission.THREAD_ASSIGN not in held[role]
        assert Permission.THREAD_END_SHIFT not in held[role]
    for role in (Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT):
        assert Permission.THREAD_CLAIM not in held[role], "reception and the accountant never hold a thread"


def test_thread_locked_is_a_409_and_the_live_event_exists() -> None:
    assert ErrorCode.THREAD_LOCKED.value == "thread_locked"
    assert ERROR_HTTP_STATUS[ErrorCode.THREAD_LOCKED] == 409
    assert LiveEventType.ASSIGNMENT_CHANGED.value == "assignment.changed"


def test_a_takeover_needs_a_reason() -> None:
    with pytest.raises(ValidationError):
        TakeoverRequest(reason="   ")
    with pytest.raises(ValidationError):
        TakeoverRequest()  # type: ignore[call-arg]
    assert TakeoverRequest(reason="  Bác sĩ cần trả lời  ").reason == "Bác sĩ cần trả lời"


# ------------------------------------------------------------- presence: the holder is separate
class _Presence:
    def __init__(self, present: dict[UUID, list[PresenceEntry]]) -> None:
        self._present = present

    async def viewers(self, conversation_ids: Any) -> dict[UUID, list[PresenceEntry]]:
        return {cid: self._present[cid] for cid in conversation_ids if cid in self._present}


def _summary(conversation_id: UUID, holder: UUID | None) -> ConversationSummary:
    return ConversationSummary.model_validate(
        {
            "id": conversation_id,
            "channel": "zalo_personal",
            "patient_id": None,
            "patient_code": None,
            "patient_display_name": None,
            "status": "open",
            "assigned_user_id": holder,
            "version": 1,
        }
    )


async def test_the_holder_is_reported_apart_from_the_viewers() -> None:
    caller, holder = UUID(int=1), UUID(int=2)
    held, other = uuid4(), uuid4()
    live = SimpleNamespace(presence=_Presence({held: [PresenceEntry(holder, PresenceState.REPLYING)]}))
    ctx = ActionContext(clinic_id=UUID(int=9), actor_type=ActorType.USER, actor_user_id=caller)
    # nobody but the holder is present, so the names query (the only use of the database) is never made
    first, second = await with_viewers(
        cast(Any, None), ctx, cast(Any, live), [_summary(held, holder), _summary(other, holder)]
    )
    assert first.holder_presence is PresenceState.REPLYING
    assert first.viewers == []
    assert second.holder_presence is None
