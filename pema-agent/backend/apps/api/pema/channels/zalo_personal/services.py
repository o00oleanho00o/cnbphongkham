"""The objects the C2 routers need, gathered in one container the composition root (package G) installs.

New module. The routers of the original (``account-routes.ts``, ``friend-routes.ts``) imported their
stores and the
account manager directly. Here they reach everything through ``C2Services`` stored in
``app.state.c2_services``, so
the routers import no other package and a test builds the container from fakes. Until the container is
installed
every C2 route answers ``501 not_implemented`` like the rest of the skeleton (the skeleton test relies on it).

``authorize`` is the seam to the session/RBAC layer of package B1: ``await authorize(request,
permission)`` returns
the ``ActionContext`` of the caller (clinic, user, role) or raises ``DomainError(UNAUTHENTICATED |
FORBIDDEN)``.
Routes call it BEFORE anything else (deny by default). Permissions used: ``admin.accounts`` (accounts,
QR, friends),
``admin.channels`` (channel settings) and ``admin.kill_switch``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fastapi import Request

from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.audit_writer import AuditSink
from pema.channels.zalo_personal.bridge_events import BridgeEventHandler
from pema.channels.zalo_personal.channel_settings import ChannelSettingsRepository
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.friend_request_store import FriendRequestPort
from pema.channels.zalo_personal.qr_login_manager import QrLoginManager
from pema_contracts.actions import ActionContext
from pema_contracts.agents import AccountStore, AgentStore
from pema_contracts.channel import ChannelRegistry
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

type Authorize = Callable[[Request, Permission], Awaitable[ActionContext]]
type ClinicResolver = Callable[[str], Awaitable[UUID | None]]


class AccountLifecycle(Protocol):
    """Start/stop of a Bot account (package C1 ``bot_account_runner``): the account routes of this
    package also
    serve Bot accounts (one ``PATCH`` for both kinds) but do not own their lifecycle."""

    async def start(self, clinic_id: UUID, account_id: str) -> None: ...

    async def stop(self, clinic_id: UUID, account_id: str) -> None: ...


@dataclass
class C2Services:
    flag_enabled: Callable[[], bool]
    """``PEMA_ZALO_PERSONAL_ENABLED``: off means no traffic at all."""
    bridge_secret: Callable[[], str | None]
    authorize: Authorize
    resolve_clinic: ClinicResolver
    """Webhook path segment (clinic slug, or the clinic id as text) -> clinic id, ``None`` when
    unknown/inactive."""
    accounts: AccountStore
    agents: AgentStore
    vault: CredentialVault
    manager: AccountManager
    qr: QrLoginManager
    friends: FriendRequestPort
    settings: ChannelSettingsRepository
    audit: AuditSink
    registry: ChannelRegistry
    events: BridgeEventHandler
    bot_lifecycle: AccountLifecycle | None = None


def get_c2(request: Request) -> C2Services:
    """The installed container, or ``501`` while the composition root has not installed one."""
    services = getattr(request.app.state, "c2_services", None)
    if not isinstance(services, C2Services):
        raise DomainError(ErrorCode.NOT_IMPLEMENTED, "Chức năng chưa được triển khai.")
    return services
