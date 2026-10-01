"""The intake side: from a Zalo update to a ``TurnJob`` on the queue (package G, no TS source).

CONTRACTS-AI01 section 4: the webhook (API process) or the poller (the listening process) hands an update to a
router, which applies the allowlist, writes the message to history AND to the Inbox of record, and puts it in
the batcher; a closed batch becomes a ``TurnJob`` on the Redis queue and a WORKER runs the turn.

Two stacks, one per channel family:

* ``build_bot_stack``: the Zalo Bot API (C1): router, batcher, webhook service, account manager and admin;
* ``build_personal_stack``: the personal account behind the Node bridge (C2): ``C2Services`` with the
  bridge client, the account manager, the QR login and the bridge event handler.

Both processes build the stacks (the worker sends replies through the channels its manager registers; a
polling bot account is listened to by the worker), but only ONE of the two listens to a given bot account:
webhook mode -> the API, polling mode -> the worker (``listen`` below).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from pema.channels.busy_wait_notice import ReplySender
from pema.channels.payload_anomaly_watch import report_payload_anomalies
from pema.channels.record_incoming_message import (
    gan_anh_vao_history,
    ghi_tin_den_vao_history,
    webhook_action_context,
)
from pema.channels.send_reply_in_parts import send_reply_in_parts
from pema.channels.zalo_bot.bot_account_admin import BotAccountAdminService
from pema.channels.zalo_bot.bot_account_manager import BotAccountManager
from pema.channels.zalo_bot.bot_account_runner import ClientFactory
from pema.channels.zalo_bot.bot_message_router import BotMessageRouter, BotRouterDeps, make_turn_job_handler
from pema.channels.zalo_bot.settings import ZaloBotSettings, get_zalo_bot_settings
from pema.channels.zalo_bot.webhook import PostgresUpdateDedupe, ZaloBotWebhookService
from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.audit_writer import SqlAuditSink
from pema.channels.zalo_personal.bridge_client import HttpBridgeClient
from pema.channels.zalo_personal.bridge_events import BridgeEventHandler, SqlUpdateDedupe
from pema.channels.zalo_personal.channel_settings import (
    ChannelPolicyReader,
    ChannelSettingsRepository,
    WorkerChannelPolicyReader,
)
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.friend_request_store import FriendRequestStore
from pema.channels.zalo_personal.incoming_message_router import RespondDecision, RouterDeps
from pema.channels.zalo_personal.qr_login_manager import build_qr_manager
from pema.channels.zalo_personal.services import C2Services
from pema.composition.auth_bridge import resolve_staff_context
from pema.composition.runtime import ProcessRole, Runtime
from pema.config.env import Settings
from pema.middleware.allowlist_filter import should_respond
from pema.middleware.message_batcher import MessageBatcher
from pema.middleware.thread_run_chain import QueueThreadRunner, ThreadRef
from pema.scheduler.proactive_send_counter_store import ProactiveSendCounterStore
from pema.scheduler.proactive_send_guard import PgProactiveSendGuard
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import InboundMessage

log = create_logger("composition.intake")

type ClinicResolver = Callable[[str], Awaitable[UUID | None]]


def make_clinic_resolver(rt: Runtime) -> ClinicResolver:
    """Webhook path segment -> clinic id. The segment is the clinic slug, or the clinic id as text (the
    worker, which cannot read ``clinic.*``, only knows the id). ``None`` for an unknown or inactive clinic."""

    async def resolve(segment: str) -> UUID | None:
        try:
            wanted = UUID(segment)
        except ValueError:
            return await rt.db.resolve_clinic(segment)
        return wanted if wanted in await rt.db.list_active_clinic_ids() else None

    return resolve


def make_batcher(rt: Runtime) -> MessageBatcher:
    """The batcher of this process: Redis store, no in-process thread runner (the turn runs in the worker),
    a closed batch becomes a ``TurnJob``."""
    return MessageBatcher(
        rt.pending_store,
        QueueThreadRunner(rt.chain),
        default_handler=make_turn_job_handler(rt.turn_queue),
    )


# ------------------------------------------------------------------------------------------ bot (C1)


@dataclass
class BotStack:
    batcher: MessageBatcher
    router: BotMessageRouter
    manager: BotAccountManager
    admin: BotAccountAdminService
    webhook: ZaloBotWebhookService
    dedupe: PostgresUpdateDedupe
    settings: ZaloBotSettings


def listens_to_bot_accounts(role: ProcessRole, mode: str) -> bool:
    """Webhook mode: the API registers the webhook and receives the updates. Polling mode: the worker polls.
    The other process only keeps the channel object to SEND (``listen=False``)."""
    return (role is ProcessRole.API) == (mode == "webhook")


def build_bot_stack(
    rt: Runtime, batcher: MessageBatcher | None = None, *, client_factory: ClientFactory | None = None
) -> BotStack:
    """``client_factory`` replaces the real Bot API client (the integration tests give a fake one)."""
    bot_settings = get_zalo_bot_settings()
    batcher = batcher or make_batcher(rt)
    send_in_parts: ReplySender = send_reply_in_parts
    router = BotMessageRouter(
        BotRouterDeps(
            accounts=rt.accounts,
            conversation=rt.conversation,
            batcher=batcher,
            thread_busy=rt.chain,
            inbox=rt.clinic_actions,
            agents=rt.agents,
            persist_images=rt.media_images.persist,
            send_in_parts=send_in_parts,
        )
    )
    channel_settings = ChannelSettingsRepository(rt.db)
    manager = BotAccountManager(
        accounts=rt.accounts,
        router=router,
        registry=rt.channels,
        settings=bot_settings,
        clinic_slug_of=channel_settings.clinic_slug,
        client_factory=client_factory,
        listen=listens_to_bot_accounts(rt.role, bot_settings.mode),
    )
    dedupe = PostgresUpdateDedupe(rt.db)
    webhook = ZaloBotWebhookService(
        resolve_clinic=make_clinic_resolver(rt), registry=rt.channels, router=router, dedupe=dedupe
    )
    admin = BotAccountAdminService(accounts=rt.accounts, manager=manager, client_factory=client_factory)
    return BotStack(batcher, router, manager, admin, webhook, dedupe, bot_settings)


# ------------------------------------------------------------------------------- personal (C2)


class _BatcherForPersonal:
    """``MessageBatcher`` seam of C2 (``enqueue_message(clinic_id, thread_key, msg)``) over C1's batcher.

    The key of C1's batcher is the ``ThreadRef`` of (clinic, account, thread)."""

    def __init__(self, batcher: MessageBatcher) -> None:
        self._batcher = batcher

    async def enqueue_message(self, clinic_id: UUID, thread_key: str, msg: InboundMessage, /) -> bool:
        return await self._batcher.enqueue_message(
            ThreadRef(clinic_id, msg.account_id, msg.thread_id).key, msg
        )


class _BlockedListener:
    """``ChannelBlockedListener``: the kill switch of the channel already stops every proactive send with a
    recognisable code, and a job whose account is not running keeps its run slot, so the scheduler needs
    nothing more; the event is logged for the operator."""

    async def on_channel_blocked(self, clinic_id: UUID, account_id: str, state: str, /) -> None:
        log.warning("personal channel blocked", account_id=account_id, state=state)


@dataclass
class PersonalStack:
    services: C2Services
    manager: AccountManager
    bridge: HttpBridgeClient


class _BotLifecycle:
    """``AccountLifecycle`` of C2's account routes for a BOT account: the one ``PATCH`` serves both kinds but
    the bot accounts are started by C1's manager."""

    def __init__(self, rt: Runtime, manager: BotAccountManager) -> None:
        self._rt = rt
        self._manager = manager

    async def start(self, clinic_id: UUID, account_id: str) -> None:
        config = await self._rt.accounts.get_account(clinic_id, account_id)
        if config is not None:
            await self._manager.start(config)

    async def stop(self, clinic_id: UUID, account_id: str) -> None:
        await self._manager.stop(clinic_id, account_id)


def build_personal_stack(
    rt: Runtime,
    batcher: MessageBatcher | None = None,
    *,
    settings: Settings | None = None,
    bot_manager: BotAccountManager | None = None,
) -> PersonalStack:
    config = settings or rt.settings
    batcher = batcher or make_batcher(rt)
    secret = config.zalo_bridge_secret.get_secret_value() if config.zalo_bridge_secret else ""
    bridge = HttpBridgeClient(config.zalo_bridge_url, secret)
    vault = CredentialVault(rt.accounts)
    policy_reader: ChannelPolicyReader
    channel_settings = ChannelSettingsRepository(rt.db)
    policy_reader = channel_settings if rt.role is ProcessRole.API else WorkerChannelPolicyReader(rt.db)
    counters = ProactiveSendCounterStore(rt.db)

    def flag_enabled() -> bool:
        return config.zalo_personal_enabled

    def bridge_secret() -> str | None:
        return secret or None

    manager = AccountManager(
        accounts=rt.accounts,
        vault=vault,
        bridge=bridge,
        registry=rt.channels,
        policy_reader=policy_reader,
        flag_enabled=flag_enabled,
        bridge_secret=bridge_secret,
        counter_for=lambda clinic_id: PgProactiveSendGuard(counters, clinic_id),
    )
    qr = build_qr_manager(bridge, manager, rt.accounts, _clinic_ref)

    async def record_incoming(clinic_id: UUID, msg: InboundMessage, /, *, luu_anh_ngay: bool) -> int:
        recorded = await ghi_tin_den_vao_history(
            clinic_id=clinic_id,
            account_id=msg.account_id,
            msg=msg,
            luu_anh_ngay=luu_anh_ngay,
            history=rt.conversation,
            inbox=rt.clinic_actions,
            ctx=webhook_action_context(clinic_id),
            persist_images=rt.media_images.persist,
        )
        return recorded.history_row_id or 0

    async def attach_images(clinic_id: UUID, msg: InboundMessage, /) -> None:
        await gan_anh_vao_history(clinic_id, rt.conversation, [msg])

    def decide(account: AccountConfig, msg: InboundMessage, bot_enabled: bool, /) -> RespondDecision:
        decision = should_respond(account, msg, bot_enabled)
        return RespondDecision(respond=decision.respond, record=decision.record, reason=decision.reason)

    def report_anomalies(account_id: str, msg: InboundMessage, /) -> None:
        report_payload_anomalies(account_id, msg)

    router_deps = RouterDeps(
        accounts=rt.accounts,
        contacts=rt.conversation,
        threads=rt.conversation,
        thread_names=rt.conversation,
        should_respond=decide,
        record_incoming=record_incoming,
        report_anomalies=report_anomalies,
        batcher=_BatcherForPersonal(batcher),
        busy_notifier=None,
        persist_images=rt.media_images.persist,
        attach_images=attach_images,
    )
    friends = FriendRequestStore(rt.db)
    audit = SqlAuditSink(rt.db)
    events = BridgeEventHandler(
        manager=manager,
        router_deps=router_deps,
        vault=vault,
        friends=friends,
        settings=channel_settings,
        dedupe=SqlUpdateDedupe(rt.db),
        listeners=[_BlockedListener()],
    )
    services = C2Services(
        flag_enabled=flag_enabled,
        bridge_secret=bridge_secret,
        authorize=resolve_staff_context,
        resolve_clinic=make_clinic_resolver(rt),
        accounts=rt.accounts,
        agents=rt.agents,
        vault=vault,
        manager=manager,
        qr=qr,
        friends=friends,
        settings=channel_settings,
        audit=audit,
        registry=rt.channels,
        events=events,
        bot_lifecycle=None if bot_manager is None else _BotLifecycle(rt, bot_manager),
    )
    return PersonalStack(services, manager, bridge)


async def _clinic_ref(clinic_id: UUID) -> str:
    """The id as text: the webhook path accepts it, and the worker cannot read the slug."""
    return str(clinic_id)
