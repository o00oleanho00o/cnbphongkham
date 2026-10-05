# ported from: src/zalo/account-manager.ts (getRunningAccountKenh / isAccountRunning, the registry part only)
"""In-memory registry of the channels that are running in THIS process.

Package A provides only the registry (the lookup the scheduler and the tools need); starting and stopping
an account stays with C1 (``zalo_bot.bot_account_runner``) and C2 (``zalo_personal.account_manager``), which
call ``register`` / ``unregister``. Keys are ``(clinic_id, account_id)`` because account ids are unique per
clinic only.

Process-local on purpose: a worker process that sends only has the channels it started. Which process owns
which account is a deployment decision of package F/G (one worker per clinic is the pilot default).
"""

from __future__ import annotations

from uuid import UUID

from pema_contracts.channel import ChannelPort


class InMemoryChannelRegistry:
    def __init__(self) -> None:
        self._running: dict[tuple[UUID, str], ChannelPort] = {}

    def register(self, clinic_id: UUID, channel: ChannelPort) -> None:
        self._running[(clinic_id, channel.account_id)] = channel

    def unregister(self, clinic_id: UUID, account_id: str) -> None:
        self._running.pop((clinic_id, account_id), None)

    def get_running(self, clinic_id: UUID, account_id: str) -> ChannelPort | None:
        return self._running.get((clinic_id, account_id))

    def list_running(self, clinic_id: UUID) -> list[ChannelPort]:
        return [ch for (clinic, _), ch in self._running.items() if clinic == clinic_id]
