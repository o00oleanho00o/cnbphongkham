from __future__ import annotations

from uuid import uuid4

from pema.channels.registry import InMemoryChannelRegistry
from pema_contracts.channel import ChannelCapabilities, ChannelKind, ChannelRegistry
from pema_contracts.testing import FakeChannel


def _channel(account: str, kind: ChannelKind = ChannelKind.ZALO_BOT) -> FakeChannel:
    return FakeChannel(caps=ChannelCapabilities(channel=kind, can_send_proactive=True), account=account)


def test_registry_satisfies_the_protocol_and_scopes_by_clinic() -> None:
    concrete = InMemoryChannelRegistry()
    registry: ChannelRegistry = concrete
    clinic_a, clinic_b = uuid4(), uuid4()
    bot = _channel("bot-1")
    concrete.register(clinic_a, bot)
    assert registry.get_running(clinic_a, "bot-1") is bot
    assert registry.get_running(clinic_b, "bot-1") is None, "ids are unique per clinic only"
    assert registry.get_running(clinic_a, "other") is None
    assert registry.list_running(clinic_a) == [bot]
    assert registry.list_running(clinic_b) == []


def test_unregister_makes_the_account_not_running() -> None:
    registry = InMemoryChannelRegistry()
    clinic = uuid4()
    registry.register(clinic, _channel("bot-1"))
    registry.unregister(clinic, "bot-1")
    assert registry.get_running(clinic, "bot-1") is None
    registry.unregister(clinic, "bot-1")  # idempotent
