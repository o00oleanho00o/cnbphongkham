"""Security scans of the shared inbox (package O, step O7). New tests, no zalo-agent original.

Four scans, written as tests so a later change that breaks one fails the build:

1. **Credential boundary.** Every response schema of the OpenAPI document is scanned for a field whose name
   could hold a credential (a broader pattern than the identity test of O1), against a short, named allow-list.
   A log capture around the whole notification chain, with marker values planted where a credential or a
   recipient lives (the bell id, a push token, the group id, the on-call number), finds no marker, no push
   token and no recipient in any log line. With a database: the audit log and the outbox hold no planted
   ``*_enc`` marker after the whole assignment flow.
2. **PII guard over every notification kind.** Every ``AssignmentKind`` and every ``HandoffNoticeEvent``, in every
   urgency, is turned into the text of the bell and the group and into the push message with the patient's name,
   phone number, e-mail, national id and address planted in every place a name could come from; none of it may
   appear, the text outside the link passes the PII mask unchanged, and the payload has no field outside
   ``NotificationPayload``.
3. **The internal account is never customer-facing.** The queue, the delivery and the clinic action refuse it; the
   internal sender refuses a customer thread and a notifier that is not ``internal``.
4. **Accountant and reception cannot claim or send.** By the permission matrix, by the actions (denied before the
   database is touched) and, with a database, by HTTP; the agent holds no claim permission; an assignment target
   is an operator only.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from evals.ops.db_support import insert_account, new_threads, staff_context
from evals.ops.invariants import no_marker_in_audit_or_outbox
from pema.agent.testing import make_caps
from pema.bootstrap import create_app
from pema.channels.identity_send_queue import (
    IdentitySendQueue,
    InMemorySendSlotBackend,
    install_identity_send_queue,
)
from pema.channels.registry import InMemoryChannelRegistry
from pema.clinic.actions import assignment, conversations
from pema.clinic.actions.notifications import (
    UnsafeNotificationPayloadError,
    deep_link,
    handoff_payload,
    serialize_payload,
    short_code,
    summary_of,
)
from pema.clinic.actions.outbound import OutboundRequest
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.rbac import ASSIGNABLE_ROLES, ROLE_PERMISSIONS
from pema.clinic.rbac.matrix import AGENT_PERMISSIONS
from pema.composition.outbound import RegistryOutboundDelivery
from pema.core.db import ClinicDatabase
from pema.notify.consumer import NotificationConsumer
from pema.notify.internal import InternalZaloSender
from pema.notify.providers import (
    FakePushProvider,
    InAppProvider,
    OnCallBellProvider,
    TeamGroupProvider,
    ZaloBellProvider,
)
from pema.notify.testing import (
    EPOCH,
    FakeClock,
    FakeInternalDirectory,
    FakeInternalSender,
    InMemoryChainStore,
    payload,
    settings,
    target,
)
from pema.notify.text import render_chat_text, render_push
from pema.notify.types import (
    ERR_ACCOUNT_NOT_RUNNING,
    ERR_CUSTOMER_RECIPIENT,
    ERR_NO_INTERNAL_ACCOUNT,
    ERR_NOT_INTERNAL,
    InternalTarget,
    InternalTargetKind,
)
from pema.policy.pii import mask_pii
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.channel import ChannelKind, SendStatus
from pema_contracts.conversations import MessageCreate, SenderType
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import (
    AssignmentKind,
    AssignRequest,
    ClaimRequest,
    EffectiveLimits,
    HandoffNoticeEvent,
    IdentityOut,
    IdentityPurpose,
    LimitOverrides,
    NotificationPayload,
    NotificationRecipientKind,
    NotificationUrgency,
    PushPlatform,
    ReleaseRequest,
    TakeoverRequest,
)
from pema_contracts.roles import ActorType, Permission, Role
from pema_contracts.testing import FAKE_CLINIC_ID, FakeChannel, InMemoryAccountStore, fake_account_config

# ================================================================================ 1. credential boundary
CREDENTIAL_LOOKING = re.compile(
    r"(_enc$|cookie|imei|user_?agent|webhook|secret|password|credential|token|signature|(^|_)qr|private_key|api_key)",
    re.IGNORECASE,
)
ALLOWED_RESPONSE_FIELDS: dict[tuple[str, str], str] = {
    (
        "AccountOut",
        "has_credentials",
    ): "a boolean 'this account has a login'; manager-only /admin/accounts (C2)",
    ("QrLoginStatus", "qr_png_base64"): "the QR the manager scans on the bridge host; /admin/accounts (C2)",
    ("AccountOut", "has_bot_token"): "a boolean; /admin/accounts",
    ("AccountStats", "tokens_today"): "a count of model tokens used, not a credential",
    ("DailyUsage", "input_tokens"): "a count of model tokens used",
    ("DailyUsage", "output_tokens"): "a count of model tokens used",
    ("TraceStepRow", "input_tokens"): "a count of model tokens used",
    ("TraceStepRow", "output_tokens"): "a count of model tokens used",
    ("TraceTurnRow", "input_tokens"): "a count of model tokens used",
    ("TraceTurnRow", "output_tokens"): "a count of model tokens used",
    ("TraceTurnRow", "total_tokens"): "a count of model tokens used",
    ("TuningItem", "token_estimate_hint"): "a hint text about token counts",
    ("LlmSettingsOut", "api_key_masked"): "'sk-ab...wxyz' (mask_secret): which key, not the key; admin.model",
    ("VisionSettingsOut", "api_key_masked"): "same mask; admin.model",
    ("ImageGenSettingsOut", "api_key_masked"): "same mask; admin.tools",
    ("ToolChainSettings", "brave_api_key_set"): "a boolean 'a search key is set'; admin.tools",
}
"""Response fields whose name looks like a credential and are accepted, each with its reason. Anything new that
matches the pattern fails the scan until somebody reads it and adds it here with a reason."""


def _properties(schema: Any) -> list[str]:
    body = cast(dict[str, Any], schema or {})
    return list(cast(dict[str, Any], body.get("properties", {})))


def _response_schemas(spec: dict[str, Any]) -> set[str]:
    seen: set[str] = set()
    schemas = cast(dict[str, Any], spec["components"]["schemas"])

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            fields = cast(dict[str, Any], node)
            ref = fields.get("$ref")
            if isinstance(ref, str):
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    visit(schemas.get(name, {}))
            for value in fields.values():
                visit(value)
        elif isinstance(node, list):
            for item in cast(list[Any], node):
                visit(item)

    for item in cast(dict[str, Any], spec["paths"]).values():
        for operation in cast(dict[str, Any], item).values():
            if isinstance(operation, dict):
                visit(cast(dict[str, Any], operation).get("responses", {}))
    return seen


def test_no_response_schema_has_a_credential_looking_field_beyond_the_named_allow_list() -> None:
    spec = create_app().openapi()
    names = _response_schemas(spec)
    assert len(names) > 100, "the scan must really walk the API"
    found = {
        (name, prop)
        for name in names
        for prop in _properties(spec["components"]["schemas"].get(name))
        if CREDENTIAL_LOOKING.search(prop)
    }
    assert found == set(ALLOWED_RESPONSE_FIELDS), (
        f"unreviewed credential-looking response fields: {sorted(found - set(ALLOWED_RESPONSE_FIELDS))}"
    )


def test_a_push_token_is_something_an_operator_sends_never_something_the_api_returns() -> None:
    spec = create_app().openapi()
    request_only = {"PushTokenIn"}
    assert request_only <= set(spec["components"]["schemas"])
    assert not request_only & _response_schemas(spec)
    returned = _properties(spec["components"]["schemas"]["PushTokenOut"])
    assert set(returned) == {"id", "platform", "last_seen"}


def test_the_notification_responses_have_no_field_outside_the_pii_free_contract() -> None:
    spec = create_app().openapi()
    notice = _properties(spec["components"]["schemas"]["NoticeOut"])
    assert set(notice) == {"id", "kind", "state", "created_at", "acked_at", "payload"}
    assert set(_properties(spec["components"]["schemas"]["NotificationPayload"])) == set(
        NotificationPayload.model_fields
    )


MARKERS = {
    "bell": "ZALO-ID-MARKER-41ac",
    "push": "PUSH-TOKEN-MARKER-9e12",
    "group": "GROUP-ID-MARKER-77d0",
    "oncall": "ONCALL-NUMBER-MARKER-5b3f",
}


async def test_the_whole_notification_chain_logs_no_recipient_and_no_token(
    caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    from pema.care.routing_types import OnCallRow
    from pema.clinic.actions.notification_chain import PushTarget

    clock = FakeClock(EPOCH)
    store = InMemoryChainStore(clock)
    store.settings = settings(push_enabled=True, team_group_id=MARKERS["group"])
    user = uuid4()
    store.targets[user] = target(
        user, zalo=MARKERS["bell"], pushes=(PushTarget(uuid4(), PushPlatform.ANDROID, MARKERS["push"]),)
    )
    store.on_call = [
        OnCallRow(
            id=UUID(int=7),
            zalo_number=MARKERS["oncall"],
            owner="Trực (mẫu)",
            valid_from=EPOCH.replace(month=1),
        )
    ]
    sender = FakeInternalSender()
    consumer = NotificationConsumer(
        store=store,
        in_app=InAppProvider(emit=lambda kind, ident: None),
        bell=ZaloBellProvider(sender),
        group=TeamGroupProvider(sender),
        on_call=OnCallBellProvider(sender),
        push=FakePushProvider(),
        clock=clock,
    )
    with caplog.at_level(logging.DEBUG):
        for kind, recipient in (
            (NotificationRecipientKind.USER, user),
            (NotificationRecipientKind.TEAM_GROUP, None),
            (NotificationRecipientKind.ON_CALL, None),
        ):
            store.add(kind, recipient, body=payload())
        await consumer.run_once()
        clock.advance(seconds=200)
        await consumer.run_once()
        sender.raises = RuntimeError("synthetic transport failure")  # the error path logs as well
        store.add(NotificationRecipientKind.USER, user, body=payload())
        store.add(NotificationRecipientKind.TEAM_GROUP, None, body=payload())
        await consumer.run_once()
        clock.advance(seconds=200)
        await consumer.run_once()

    assert sender.sent, "the chain really ran"
    captured = capfd.readouterr()
    everything = "\n".join(record.getMessage() + repr(record.__dict__) for record in caplog.records)
    everything += captured.out + captured.err
    for marker in MARKERS.values():
        assert marker not in everything
    assert not re.search(r"_enc\b|cookie", everything, re.IGNORECASE)


async def test_the_internal_sender_logs_no_recipient_when_it_refuses(
    caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    registry = InMemoryChannelRegistry()
    notifier = FakeChannel(caps=make_caps(), account="bell")
    registry.register(FAKE_CLINIC_ID, notifier)
    customer_ref = "customer-thread-MARKER-2c9d"
    directory = FakeInternalDirectory(customer_refs=frozenset({customer_ref}))
    sender = InternalZaloSender(FAKE_CLINIC_ID, registry, directory)
    with caplog.at_level(logging.DEBUG):
        refused = await sender.send(InternalTarget(InternalTargetKind.STAFF, customer_ref), "[Pema] thử")
        directory.purpose = "customer"
        wrong = await sender.send(InternalTarget(InternalTargetKind.STAFF, MARKERS["bell"]), "[Pema] thử")
    assert refused.error_code == ERR_CUSTOMER_RECIPIENT
    assert wrong.error_code == ERR_NOT_INTERNAL
    assert notifier.sent == []
    everything = "\n".join(record.getMessage() + repr(record.__dict__) for record in caplog.records)
    everything += "".join(capfd.readouterr())
    assert customer_ref not in everything
    assert MARKERS["bell"] not in everything


# ===================================================================================== 2. PII guard
PATIENT_NAME = "Nguyễn Thị Hoa (mẫu)"
CUSTOMER_NAME = "Hoa Mẫu Zalo"
PLANTED_PII = ("0912345678", "hoa.mau@example.test", "012345678901", "12 Phố Mẫu, Quận 1", "Nguyễn Thị Hoa")
LINK_MARK = "\nMở: "
BASE_URL = "https://pema.example.test"
EXPECTED_FIELDS = {
    "event",
    "short_code",
    "identity_label",
    "urgency",
    "summary",
    "deep_link",
    "from_user_id",
    "to_user_id",
    "request_id",
    "position",
    "sla_due_at",
    "oncall_id",
}


def _assert_pii_free(data: dict[str, Any]) -> None:
    chat = render_chat_text(data, BASE_URL)
    body, _, link = chat.partition(LINK_MARK)
    assert link.startswith(BASE_URL + "/"), "one link line, behind the login"
    push = render_push(data)
    for blob in (
        chat,
        push.title,
        push.body,
        push.deep_link,
        push.short_code,
        json.dumps(data, ensure_ascii=False),
    ):
        for planted in (*PLANTED_PII, PATIENT_NAME, CUSTOMER_NAME):
            assert planted not in blob
    assert not mask_pii(body).changed, "the text of the bell and the group passes the PII mask unchanged"
    assert not mask_pii(push.body).changed
    assert set(data) <= EXPECTED_FIELDS
    assert len(chat) < 400, "a notification is a line, never a message body"


def test_the_payload_is_a_closed_set_of_fields() -> None:
    assert set(NotificationPayload.model_fields) == EXPECTED_FIELDS
    assert NotificationPayload.model_config.get("extra") == "forbid"
    assert set(inspect.signature(summary_of).parameters) == {"kind", "conversation_id", "to_agent"}, (
        "the summary of an assignment notice is composed from the kind and the id: no message text can reach it"
    )


@pytest.mark.parametrize("kind", list(AssignmentKind))
@pytest.mark.parametrize("urgency", list(NotificationUrgency))
@pytest.mark.parametrize("to_agent", [False, True])
def test_every_assignment_notice_is_pii_free(
    kind: AssignmentKind, urgency: NotificationUrgency, to_agent: bool
) -> None:
    conversation = uuid4()
    built = NotificationPayload(
        event=kind,
        short_code=short_code(conversation),
        identity_label="Long",
        urgency=urgency,
        summary=summary_of(kind, conversation, to_agent=to_agent),
        deep_link=deep_link(conversation),
        from_user_id=uuid4(),
        to_user_id=uuid4(),
    )
    data = serialize_payload(built, forbidden_names=[PATIENT_NAME, CUSTOMER_NAME])
    _assert_pii_free(data)


@pytest.mark.parametrize("event", list(HandoffNoticeEvent))
@pytest.mark.parametrize("urgency", ["normal", "urgent", "critical"])
@pytest.mark.parametrize("depth", ["D2", "D5", f"{PATIENT_NAME} 0912345678"])
def test_every_handoff_notice_is_pii_free_even_when_the_depth_text_is_not(
    event: HandoffNoticeEvent, urgency: str, depth: str
) -> None:
    from datetime import timedelta

    data = handoff_payload(
        request_id=uuid4(),
        urgency=urgency,
        depth=depth,
        position=1,
        sla_due_at=EPOCH + timedelta(minutes=30),
        on_call=event is HandoffNoticeEvent.HANDOFF_ON_CALL,
        oncall_id=uuid4(),
        to_user_id=uuid4(),
    )
    _assert_pii_free(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", f"Hội thoại của {PATIENT_NAME}"),
        ("summary", "Gọi lại số 0912345678"),
        ("summary", "Gửi tới hoa.mau@example.test"),
        ("summary", "CCCD 012345678901"),
        ("identity_label", PATIENT_NAME),
        ("identity_label", CUSTOMER_NAME),
    ],
)
def test_a_payload_that_carries_personal_data_is_refused_and_the_error_does_not_repeat_it(
    field: str, value: str
) -> None:
    conversation = uuid4()
    fields: dict[str, Any] = {
        "event": AssignmentKind.TAKEOVER,
        "short_code": short_code(conversation),
        "identity_label": "Long",
        "summary": summary_of(AssignmentKind.TAKEOVER, conversation),
        "deep_link": deep_link(conversation),
    }
    fields[field] = value
    with pytest.raises(UnsafeNotificationPayloadError) as err:
        serialize_payload(NotificationPayload(**fields), forbidden_names=[PATIENT_NAME, CUSTOMER_NAME])
    assert value not in str(err.value)


def test_the_text_renderer_refuses_a_row_that_skipped_the_serializer() -> None:
    from pema.notify.text import UnsafeTextError

    row = payload(summary="Gọi lại số 0912345678 giúp em")
    with pytest.raises(UnsafeTextError) as err:
        render_chat_text(row, BASE_URL)
    assert "0912345678" not in str(err.value)
    with pytest.raises(UnsafeTextError):
        render_push(row)


# ============================================================ 3. the internal account, never customer-facing
def _identity(account_id: str, purpose: IdentityPurpose) -> IdentityOut:
    return IdentityOut(
        id=account_id,
        label=f"Danh tính {account_id}",
        channel=ChannelKind.ZALO_PERSONAL,
        purpose=purpose,
        enabled=True,
        channel_enabled=True,
        kill_switch_on=False,
        bridge_state=None,
        overrides=LimitOverrides(),
        effective=EffectiveLimits(send_gap_min_s=0, send_gap_max_s=0, daily_cap=None),
    )


@pytest.fixture(autouse=True)
def _no_real_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    async def immediate(thread_key: str, task: Callable[[], Awaitable[object]]) -> object:
        return await task()

    monkeypatch.setattr("pema.channels.send_reply_in_parts.default_enqueue_send", lambda: immediate)
    install_identity_send_queue(None)


def _delivery() -> tuple[RegistryOutboundDelivery, dict[str, FakeChannel], IdentitySendQueue]:
    table = {
        "long": _identity("long", IdentityPurpose.CUSTOMER),
        "bell": _identity("bell", IdentityPurpose.INTERNAL),
    }

    async def lookup(account_id: str) -> IdentityOut | None:
        return table.get(account_id)

    queue = IdentitySendQueue(clinic_id=FAKE_CLINIC_ID, lookup=lookup, backend=InMemorySendSlotBackend())
    store = InMemoryAccountStore(
        *(fake_account_config(id=name, label=name, channel=ChannelKind.ZALO_PERSONAL) for name in table)
    )
    registry = InMemoryChannelRegistry()
    channels = {name: FakeChannel(caps=make_caps(), account=name) for name in table}
    for channel in channels.values():
        registry.register(FAKE_CLINIC_ID, channel)
    return RegistryOutboundDelivery(store, registry, None, queue), channels, queue


def _request(account_id: str | None, *, proactive: bool = False) -> OutboundRequest:
    return OutboundRequest(
        clinic_id=FAKE_CLINIC_ID,
        message_id=uuid4(),
        conversation_id=uuid4(),
        channel=ChannelKind.ZALO_PERSONAL,
        external_ref="synthetic-thread-1",
        text="Dạ em chào chị ạ.",
        proactive=proactive,
        account_id=account_id,
        sender_type=SenderType.STAFF,
        sender_user_id=uuid4(),
    )


def _system() -> ActionContext:
    return ActionContext(clinic_id=FAKE_CLINIC_ID, actor_type=ActorType.SYSTEM, source=ActionSource.SYSTEM)


async def test_the_queue_refuses_the_internal_account_for_a_customer_message() -> None:
    _, _, queue = _delivery()
    for proactive in (False, True):
        admission = await queue.admit("bell", proactive=proactive)
        assert admission.rejection is not None
        assert admission.rejection.error_code is ErrorCode.POLICY_DENIED
    assert not await queue.is_customer_facing("bell")
    assert await queue.is_customer_facing("long")


async def test_the_delivery_never_sends_a_customer_message_through_the_internal_account() -> None:
    delivery, channels, _ = _delivery()

    named = await delivery.deliver(_system(), _request("bell"))
    by_kind = await delivery.deliver(_system(), _request(None))
    proactive = await delivery.deliver(_system(), _request("bell", proactive=True))

    assert named.status is SendStatus.REJECTED and named.error_code is ErrorCode.POLICY_DENIED
    assert proactive.status is SendStatus.REJECTED and proactive.error_code is ErrorCode.POLICY_DENIED
    assert by_kind.status is SendStatus.SENT, (
        "the search by kind skips the notifier and finds the customer identity"
    )
    assert channels["bell"].sent == []
    assert len(channels["long"].sent) == 1


async def test_the_internal_sender_writes_only_through_the_internal_account_and_never_to_a_customer() -> None:
    registry = InMemoryChannelRegistry()
    channels = {name: FakeChannel(caps=make_caps(), account=name) for name in ("long", "bell")}
    for channel in channels.values():
        registry.register(FAKE_CLINIC_ID, channel)
    customer_ref = "synthetic-customer-thread"
    directory = FakeInternalDirectory(
        account_id="bell", purpose="internal", customer_refs=frozenset({customer_ref})
    )
    sender = InternalZaloSender(FAKE_CLINIC_ID, registry, directory)

    ok = await sender.send(InternalTarget(InternalTargetKind.GROUP, "synthetic-group"), "[Pema] thử")
    to_customer = await sender.send(InternalTarget(InternalTargetKind.STAFF, customer_ref), "[Pema] thử")
    directory.purpose = "customer"  # the notifier was switched back to a customer identity
    not_internal = await sender.send(
        InternalTarget(InternalTargetKind.GROUP, "synthetic-group"), "[Pema] thử"
    )
    directory.purpose, directory.account_id = "internal", None
    nothing_set_up = await sender.send(
        InternalTarget(InternalTargetKind.GROUP, "synthetic-group"), "[Pema] thử"
    )

    assert ok.status.value == "sent"
    assert to_customer.error_code == ERR_CUSTOMER_RECIPIENT
    assert not_internal.error_code == ERR_NOT_INTERNAL
    assert nothing_set_up.error_code == ERR_NO_INTERNAL_ACCOUNT
    assert channels["long"].sent == [], "the customer identity is never used for a notice"
    assert [part.thread_id for part in channels["bell"].sent] == ["synthetic-group"]
    unregistered = InternalZaloSender(FAKE_CLINIC_ID, InMemoryChannelRegistry(), FakeInternalDirectory())
    down = await unregistered.send(InternalTarget(InternalTargetKind.GROUP, "synthetic-group"), "[Pema] thử")
    assert down.error_code == ERR_ACCOUNT_NOT_RUNNING


# ================================================================ 4. accountant and reception, the agent
GUARDED = (
    Permission.THREAD_CLAIM,
    Permission.THREAD_ASSIGN,
    Permission.THREAD_END_SHIFT,
    Permission.CONVERSATION_REPLY,
)


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT])
def test_reception_the_accountant_and_the_patient_hold_no_thread_permission(role: Role) -> None:
    held = ROLE_PERMISSIONS[role]
    assert not held & set(GUARDED)
    assert Permission.NOTIFY_SELF not in held, "and they get no notification of a thread either"


def test_the_claim_and_reply_permissions_belong_to_the_operator_roles_exactly() -> None:
    claim = {role for role, held in ROLE_PERMISSIONS.items() if Permission.THREAD_CLAIM in held}
    reply = {role for role, held in ROLE_PERMISSIONS.items() if Permission.CONVERSATION_REPLY in held}
    assert claim == reply == set(ASSIGNABLE_ROLES) == {Role.OWNER, Role.MANAGER, Role.DOCTOR, Role.CS_STAFF}


def test_the_agent_holds_no_permission_to_claim_assign_or_end_a_shift() -> None:
    assert not AGENT_PERMISSIONS & {
        Permission.THREAD_CLAIM,
        Permission.THREAD_ASSIGN,
        Permission.THREAD_END_SHIFT,
    }


class ExplodingDb:
    """A database that must never be touched: a denied action stops at the permission check."""

    def session(self) -> Any:
        raise AssertionError("the database was reached before the permission check")


def _ctx(role: Role, actor: ActorType = ActorType.USER) -> ActionContext:
    return ActionContext(
        clinic_id=FAKE_CLINIC_ID,
        actor_type=actor,
        actor_user_id=uuid4() if actor is ActorType.USER else None,
        actor_role=role,
    )


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT])
async def test_the_actions_refuse_reception_the_accountant_and_the_patient_before_the_database(
    role: Role,
) -> None:
    db = cast(ClinicDatabase, ExplodingDb())
    ctx, thread, other = _ctx(role), uuid4(), uuid4()
    calls: list[Awaitable[Any]] = [
        assignment.claim(db, ctx, thread, ClaimRequest()),
        assignment.takeover(db, ctx, thread, TakeoverRequest(reason="Lý do (mẫu)")),
        assignment.release(db, ctx, thread, ReleaseRequest()),
        assignment.assign(db, ctx, thread, AssignRequest(user_id=other)),
        assignment.end_shift(db, ctx, other),
        conversations.send_message(db, ctx, thread, MessageCreate(text="Tin thử")),
    ]
    for call in calls:
        with pytest.raises(DomainError) as err:
            await call
        assert err.value.code is ErrorCode.FORBIDDEN


@pytest.mark.parametrize("actor", [ActorType.AGENT, ActorType.SCHEDULER, ActorType.SYSTEM])
async def test_nobody_but_a_signed_in_operator_can_hold_a_thread(actor: ActorType) -> None:
    db = cast(ClinicDatabase, ExplodingDb())
    ctx = _ctx(Role.OWNER, actor)
    for call in (
        assignment.claim(db, ctx, uuid4()),
        assignment.takeover(db, ctx, uuid4(), TakeoverRequest(reason="Lý do (mẫu)")),
        assignment.assign(db, ctx, uuid4(), AssignRequest(user_id=uuid4())),
    ):
        with pytest.raises(DomainError) as err:
            await call
        assert err.value.code is ErrorCode.FORBIDDEN


# ----------------------------------------------------------------------------- with a database
@pytest.mark.db
async def test_over_http_reception_and_the_accountant_get_403_on_claim_and_send(
    client_factory: Any, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    (thread,) = await new_threads(db, admin, world, 1)
    for key in ("reception.lan", "accountant.hoa"):
        client = await client_factory(key)
        claim = await client.post(f"/api/v1/conversations/{thread}/claim", json={})
        send = await client.post(f"/api/v1/conversations/{thread}/messages", json={"text": "Tin thử"})
        assert claim.status_code == 403, key
        assert send.status_code == 403, key
    operator = await client_factory("cs.maianh")
    assert (await operator.post(f"/api/v1/conversations/{thread}/claim", json={})).status_code == 200


@pytest.mark.db
async def test_a_thread_can_be_assigned_to_an_operator_and_never_to_reception_or_the_accountant(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    (thread,) = await new_threads(db, admin, world, 1)
    manager = staff_context(world, "manager")
    for key in ("reception.lan", "accountant.hoa"):
        with pytest.raises(DomainError) as err:
            await assignment.assign(db, manager, thread, AssignRequest(user_id=world.users[key]))
        assert err.value.code is ErrorCode.VALIDATION_FAILED, key
    held = await assignment.assign(db, manager, thread, AssignRequest(user_id=world.users["cs.thu"]))
    assert held.assigned_user_id == world.users["cs.thu"]


@pytest.mark.db
async def test_the_database_refuses_a_conversation_that_points_to_the_internal_account(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("bell", purpose="internal")
    (thread,) = await new_threads(db, admin, world, 1, account=None)
    with pytest.raises(DBAPIError), admin.begin() as conn:
        conn.execute(text("UPDATE clinic.conversation SET account_id = 'bell' WHERE id = :c"), {"c": thread})


@pytest.mark.db
async def test_after_a_whole_assignment_flow_no_planted_credential_is_in_the_audit_log_or_the_outbox(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    secrets = {
        "bot_token_enc": "ENC-BOT-TOKEN-MARKER-7f3a",
        "credential_enc": "ENC-COOKIE-MARKER-91bc",
        "webhook_secret_enc": "ENC-WEBHOOK-MARKER-d204",
    }
    insert_account(admin, world, "long", **secrets)
    insert_account(admin, world, "bell", purpose="internal", **secrets)
    (thread,) = await new_threads(db, admin, world, 1)
    mai, thu, manager = (staff_context(world, key) for key in ("cs.maianh", "cs.thu", "manager"))
    await assignment.claim(db, mai, thread)
    await assignment.takeover(db, thu, thread, TakeoverRequest(reason="Đổi người (mẫu)"))
    await assignment.assign(db, manager, thread, AssignRequest(user_id=world.users["doctor.mai"]))
    await assignment.release(db, manager, thread, ReleaseRequest(note="Trả lại (mẫu)"))

    assert no_marker_in_audit_or_outbox(admin, list(secrets.values())) == []
