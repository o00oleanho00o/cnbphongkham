# ported from: src/config/account-agent-stores.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The tests added at the end cover what is new in this port and has no original: ``policy_profile`` on both stores
(the restrictive one wins, the default is ``patient_channel``), the secrets, the guarded patch keys, per-clinic
isolation and the account/agent foreign key.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from pema.config import env as env_module
from pema.config.account_store import AccountStoreImpl
from pema.config.agent_store import DEFAULT_AGENT_ID, AgentStoreImpl
from pema.conversation.pg_testing import ClinicEnv
from pema_contracts.agents import AccountConfig, Allowlist, AllowlistMode, LlmProviderKind
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey

pytestmark = pytest.mark.db


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "c" * 64)
    env_module.get_settings.cache_clear()
    yield
    env_module.get_settings.cache_clear()


async def _new_account(
    accounts: AccountStoreImpl,
    env: ClinicEnv,
    account_id: str,
    label: str = "Nick test",
    agent_id: str | None = None,
) -> AccountConfig:
    return await accounts.create_account(
        env.clinic_id,
        account_id=account_id,
        label=label,
        channel=ChannelKind.ZALO_PERSONAL,
        agent_id=agent_id,
    )


# ----------------------------------------------------------------- agent-store


async def test_agent_store_ensure_default_agent_creates_once_and_returns_the_same_agent_when_called_again(
    env: ClinicEnv,
) -> None:
    """ensureDefaultAgent tạo 1 lần, gọi lại trả cùng agent"""
    agents = AgentStoreImpl(env.db)
    first = await agents.ensure_default_agent(env.clinic_id)
    second = await agents.ensure_default_agent(env.clinic_id)
    assert first.id == second.id == DEFAULT_AGENT_ID
    assert first.is_default is True
    assert await env.scalar("SELECT COUNT(*) FROM agent.agents WHERE is_default") == 1


async def test_agent_store_crud_create_edit_persona_and_model_override_read_back(env: ClinicEnv) -> None:
    """CRUD agent: tạo, sửa persona + model override, đọc lại đúng"""
    agents = AgentStoreImpl(env.db)
    await agents.create_agent(
        env.clinic_id, agent_id="tu-van", name="Tư Vấn", icon="💼", persona="Bạn là tư vấn viên"
    )

    updated = await agents.update_agent(
        env.clinic_id,
        "tu-van",
        {
            "persona": "Bạn là tư vấn viên khóa học",
            "model_provider": LlmProviderKind.ANTHROPIC,
            "model_name": "claude-sonnet-5",
            "max_steps": 4,
        },
    )
    assert updated is not None
    assert updated.persona == "Bạn là tư vấn viên khóa học"
    assert updated.model_provider == LlmProviderKind.ANTHROPIC
    assert updated.max_steps == 4
    reread = await agents.get_agent(env.clinic_id, "tu-van")
    assert reread == updated


async def test_agent_store_cannot_delete_the_default_agent_or_an_agent_in_use(env: ClinicEnv) -> None:
    """không xóa được agent mặc định hoặc agent đang được dùng"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="tu-van", name="Tư Vấn", icon="💼", persona="")
    default = await agents.ensure_default_agent(env.clinic_id)
    assert (await agents.delete_agent(env.clinic_id, default.id))[0] is False

    await _new_account(accounts, env, "acc-dung-agent", "A", "tu-van")
    ok, reason = await agents.delete_agent(env.clinic_id, "tu-van")
    assert ok is False
    assert reason is not None
    assert "account dùng" in reason


async def test_agent_store_can_delete_an_agent_nobody_uses(env: ClinicEnv) -> None:
    """xóa được agent không ai dùng"""
    agents = AgentStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="agent-le", name="Lẻ", icon="🤖", persona="")
    assert await agents.delete_agent(env.clinic_id, "agent-le") == (True, None)
    assert await agents.get_agent(env.clinic_id, "agent-le") is None


async def test_agent_store_deleting_an_agent_clears_its_kb_and_mcp_bindings_so_a_same_id_agent_starts_clean(
    env: ClinicEnv,
) -> None:
    """xóa agent dọn sạch nguồn Kho tri thức đã gán - agent tạo lại CÙNG id không đọc lại tài liệu cũ"""
    # Id agent là SLUG TẤT ĐỊNH sinh từ tên - kịch bản thật: xóa "Bán hàng" (id ban-hang) rồi tạo lại agent CÙNG TÊN
    # đó sẽ ra đúng id cũ. Ở đây việc dọn là ON DELETE CASCADE của agent_kb_document / agent_mcp_servers.
    agents = AgentStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="ban-hang", name="Bán hàng", icon="🤖", persona="")
    await env.execute(
        "INSERT INTO agent.kb_document (clinic_id, id, name, kind, raw_text) "
        "VALUES (:c, 'kb-1', 'Chính sách', 'text', 'abc')",
        c=env.clinic_id,
    )
    await env.execute(
        "INSERT INTO agent.mcp_servers (clinic_id, id, name, url) VALUES (:c, 'mcp-1', 'Máy chủ', 'http://x')",
        c=env.clinic_id,
    )
    await env.execute(
        "INSERT INTO agent.agent_kb_document (clinic_id, agent_id, source_id) VALUES (:c, 'ban-hang', 'kb-1')",
        c=env.clinic_id,
    )
    await env.execute(
        "INSERT INTO agent.agent_mcp_servers (clinic_id, agent_id, server_id) VALUES (:c, 'ban-hang', 'mcp-1')",
        c=env.clinic_id,
    )
    bound = "SELECT COUNT(*) FROM agent.agent_kb_document WHERE agent_id = 'ban-hang'"
    assert await env.scalar(bound) == 1, "chưa xóa mà đã rỗng thì test vô nghĩa"

    assert (await agents.delete_agent(env.clinic_id, "ban-hang"))[0] is True

    await agents.create_agent(env.clinic_id, agent_id="ban-hang", name="Bán hàng", icon="🤖", persona="")
    assert await env.scalar(bound) == 0, (
        "agent mới tạo (trùng id agent cũ đã xóa) không được đọc lại tài liệu của agent cũ"
    )
    assert await env.scalar("SELECT COUNT(*) FROM agent.agent_mcp_servers WHERE agent_id = 'ban-hang'") == 0
    # the documents and servers themselves stay: only the BINDING belongs to the agent
    assert await env.scalar("SELECT COUNT(*) FROM agent.kb_document WHERE id = 'kb-1'") == 1


async def test_agent_store_get_agent_for_account_falls_back_to_the_default_when_the_agent_does_not_exist(
    env: ClinicEnv,
) -> None:
    """getAgentForAccount rơi về default khi agent không tồn tại"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    account = await _new_account(accounts, env, "acc-dangling")
    dangling = account.model_copy(
        update={"agent_id": "agent-da-xoa"}
    )  # the FK makes this impossible in the DB
    agent = await agents.get_agent_for_account(env.clinic_id, dangling)
    assert agent.is_default is True


# ----------------------------------------------------------------- account-store


async def test_account_store_new_account_without_an_agent_is_attached_to_the_default_agent(
    env: ClinicEnv,
) -> None:
    """tạo account không chỉ định agent thì gắn agent mặc định"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    account = await _new_account(accounts, env, "acc-moi")
    assert account.agent_id == (await agents.ensure_default_agent(env.clinic_id)).id
    assert account.enabled is True
    assert account.group_passive_listen is True


async def test_account_store_rename_policies_and_attach_another_brain(env: ClinicEnv) -> None:
    """đổi tên + policies + gắn não khác"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="tu-van", name="Tư Vấn", icon="💼", persona="")
    await _new_account(accounts, env, "acc-moi")
    updated = await accounts.update_account(
        env.clinic_id,
        "acc-moi",
        {
            "label": "Nick đã đổi tên",
            "agent_id": "tu-van",
            "allowlist": Allowlist(mode=AllowlistMode.LIST, user_ids=["u1", "u2"]),
            "group_require_mention": False,
        },
    )
    assert updated is not None
    assert updated.label == "Nick đã đổi tên"
    assert updated.agent_id == "tu-van"
    assert updated.allowlist == Allowlist(mode=AllowlistMode.LIST, user_ids=["u1", "u2"])
    assert updated.group_require_mention is False


async def test_account_store_list_enabled_accounts_filters_the_disabled_ones(env: ClinicEnv) -> None:
    """listEnabledAccounts lọc account tắt"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-moi")
    await accounts.update_account(env.clinic_id, "acc-moi", {"enabled": False})
    assert not any(a.id == "acc-moi" for a in await accounts.list_enabled_accounts(env.clinic_id))
    assert any(a.id == "acc-moi" for a in await accounts.list_accounts(env.clinic_id))


async def test_account_store_delete_account(env: ClinicEnv) -> None:
    """xóa account"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-moi")
    assert await accounts.delete_account(env.clinic_id, "acc-moi") is True
    assert await accounts.delete_account(env.clinic_id, "acc-moi") is False


# ----------------------------------------------------------------- seed migration từ accounts.json


def _seed_path(directory: Path) -> Path:
    path = directory / "seed-accounts.json"
    path.write_text(
        json.dumps(
            {
                "accounts": [
                    {"id": "acc-persona", "label": "Có persona", "persona": "Bạn là Minh Triết"},
                    {"id": "acc-trong", "label": "Không persona"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


async def test_seed_migration_old_account_with_a_persona_becomes_its_own_agent_empty_persona_uses_default(
    env: ClinicEnv, tmp_path: Path
) -> None:
    """import account cũ: persona riêng tách thành agent riêng, rỗng dùng default"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)

    await accounts.run_accounts_seed_migration(env.clinic_id, _seed_path(tmp_path))

    with_persona = await accounts.get_account(env.clinic_id, "acc-persona")
    assert with_persona is not None
    assert with_persona.agent_id == "acc-persona-agent"
    own = await agents.get_agent(env.clinic_id, "acc-persona-agent")
    assert own is not None
    assert own.persona == "Bạn là Minh Triết"
    assert own.name == "Não của Có persona"

    without = await accounts.get_account(env.clinic_id, "acc-trong")
    assert without is not None
    assert without.agent_id == (await agents.ensure_default_agent(env.clinic_id)).id


async def test_seed_migration_is_a_no_op_when_the_accounts_table_already_has_data(
    env: ClinicEnv, tmp_path: Path
) -> None:
    """bảng accounts đã có dữ liệu thì seed là no-op"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-co-san")
    before = len(await accounts.list_accounts(env.clinic_id))

    await accounts.run_accounts_seed_migration(env.clinic_id, _seed_path(tmp_path))

    assert len(await accounts.list_accounts(env.clinic_id)) == before


async def test_seed_migration_without_a_seed_file_only_ensures_the_default_agent(
    env: ClinicEnv, tmp_path: Path
) -> None:
    """(thêm) cài mới hoàn toàn không có file seed: không phải lỗi, chỉ có agent mặc định"""
    accounts = AccountStoreImpl(env.db)
    await accounts.run_accounts_seed_migration(env.clinic_id, tmp_path / "khong-co.json")
    assert await accounts.list_accounts(env.clinic_id) == []
    assert await env.scalar("SELECT COUNT(*) FROM agent.agents WHERE is_default") == 1


# ----------------------------------------------------------------- policy_profile (new in this port)


async def test_policy_profile_defaults_to_patient_channel_on_both_stores_fail_safe(env: ClinicEnv) -> None:
    """(thêm) mặc định patient_channel ở cả account và agent"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    agent = await agents.create_agent(
        env.clinic_id, agent_id="mac-dinh-an-toan", name="A", icon="🤖", persona=""
    )
    account = await _new_account(accounts, env, "acc-an-toan")
    assert agent.policy_profile == PolicyProfileKey.PATIENT_CHANNEL
    assert account.policy_profile == PolicyProfileKey.PATIENT_CHANNEL
    assert (
        await agents.ensure_default_agent(env.clinic_id)
    ).policy_profile == PolicyProfileKey.PATIENT_CHANNEL


@pytest.mark.parametrize(
    ("account_profile", "agent_profile", "expected"),
    [
        (
            PolicyProfileKey.STAFF_ASSISTANT,
            PolicyProfileKey.STAFF_ASSISTANT,
            PolicyProfileKey.STAFF_ASSISTANT,
        ),
        (
            PolicyProfileKey.PATIENT_CHANNEL,
            PolicyProfileKey.STAFF_ASSISTANT,
            PolicyProfileKey.PATIENT_CHANNEL,
        ),
        (
            PolicyProfileKey.STAFF_ASSISTANT,
            PolicyProfileKey.PATIENT_CHANNEL,
            PolicyProfileKey.PATIENT_CHANNEL,
        ),
        (
            PolicyProfileKey.PATIENT_CHANNEL,
            PolicyProfileKey.PATIENT_CHANNEL,
            PolicyProfileKey.PATIENT_CHANNEL,
        ),
    ],
)
async def test_policy_profile_the_stricter_of_account_and_agent_wins(
    env: ClinicEnv,
    account_profile: PolicyProfileKey,
    agent_profile: PolicyProfileKey,
    expected: PolicyProfileKey,
) -> None:
    """(thêm) bên chặt hơn thắng: chỉ khi CẢ HAI là staff_assistant thì mới chạy staff_assistant"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    await agents.create_agent(
        env.clinic_id, agent_id="agent-p", name="P", icon="🤖", persona="", policy_profile=agent_profile
    )
    account = await accounts.create_account(
        env.clinic_id,
        account_id="acc-p",
        label="P",
        channel=ChannelKind.ZALO_BOT,
        agent_id="agent-p",
        policy_profile=account_profile,
    )
    assert await agents.get_effective_policy_profile(env.clinic_id, account) == expected


async def test_policy_profile_can_be_changed_on_both_stores_and_persists(env: ClinicEnv) -> None:
    """(thêm) đổi policy_profile qua update và đọc lại đúng"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="agent-p", name="P", icon="🤖", persona="")
    await _new_account(accounts, env, "acc-p", agent_id="agent-p")

    agent = await agents.update_agent(
        env.clinic_id, "agent-p", {"policy_profile": PolicyProfileKey.STAFF_ASSISTANT}
    )
    account = await accounts.update_account(
        env.clinic_id, "acc-p", {"policy_profile": PolicyProfileKey.STAFF_ASSISTANT}
    )
    assert agent is not None
    assert agent.policy_profile == PolicyProfileKey.STAFF_ASSISTANT
    assert account is not None
    assert account.policy_profile == PolicyProfileKey.STAFF_ASSISTANT
    assert (
        await agents.get_effective_policy_profile(env.clinic_id, account) == PolicyProfileKey.STAFF_ASSISTANT
    )


# ----------------------------------------------------------------- guards, secrets, isolation (new in this port)


async def test_update_agent_clearing_a_model_override_with_none_and_unknown_keys_are_refused(
    env: ClinicEnv,
) -> None:
    """(thêm) key có mặt với giá trị None là xóa override; key không được phép sửa thì bị từ chối, không nuốt lặng lẽ"""
    agents = AgentStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="tu-van", name="Tư Vấn", icon="💼", persona="")
    await agents.update_agent(env.clinic_id, "tu-van", {"model_name": "m", "max_steps": 3})
    cleared = await agents.update_agent(env.clinic_id, "tu-van", {"model_name": None, "max_steps": None})
    assert cleared is not None
    assert (cleared.model_name, cleared.max_steps) == (None, None)

    with pytest.raises(ValueError, match="is_default"):
        await agents.update_agent(env.clinic_id, "tu-van", {"is_default": True})
    assert await agents.update_agent(env.clinic_id, "khong-co", {"name": "x"}) is None


async def test_update_account_refuses_channel_id_and_token_flag_instead_of_silently_ignoring_them(
    env: ClinicEnv,
) -> None:
    """(thêm) update_account không nhận channel / has_bot_token: nhận vào là nuốt lặng lẽ rồi trả giá trị CŨ như đã lưu"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-khoa")
    for key, value in (("channel", ChannelKind.ZALO_BOT), ("has_bot_token", True), ("id", "x")):
        with pytest.raises(ValueError, match=key):
            await accounts.update_account(env.clinic_id, "acc-khoa", {key: value})
    assert await accounts.update_account(env.clinic_id, "khong-co", {"label": "x"}) is None


async def test_update_account_validates_the_values_it_stores(env: ClinicEnv) -> None:
    """(thêm) giá trị sai (delay ngoài 0..1440) bị từ chối trước khi chạm DB; agent không tồn tại bị từ chối"""
    from pydantic import ValidationError

    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-hop-le")
    with pytest.raises(ValidationError):
        await accounts.update_account(env.clinic_id, "acc-hop-le", {"auto_accept_friend_delay_minutes": 5000})
    with pytest.raises(DomainError) as raised:
        await accounts.update_account(env.clinic_id, "acc-hop-le", {"agent_id": "agent-khong-co"})
    assert raised.value.code == ErrorCode.VALIDATION_FAILED


async def test_create_account_with_a_duplicate_id_is_a_conflict(env: ClinicEnv) -> None:
    """(thêm) trùng id account là xung đột (409), không phải lỗi hệ thống"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-trung")
    with pytest.raises(DomainError) as raised:
        await _new_account(accounts, env, "acc-trung")
    assert raised.value.code == ErrorCode.INVALID_STATE


@pytest.mark.usefixtures("secret_key")
async def test_bot_token_is_stored_encrypted_returned_decrypted_and_never_in_the_dto(env: ClinicEnv) -> None:
    """(thêm) token bot mã hóa trong DB, giải mã qua đường riêng, DTO chỉ có has_bot_token; chuỗi rỗng = xóa"""
    accounts = AccountStoreImpl(env.db)
    created = await accounts.create_account(
        env.clinic_id, account_id="bot-1", label="Bot", channel=ChannelKind.ZALO_BOT, agent_id=None
    )
    assert created.has_bot_token is False
    assert await accounts.get_bot_token(env.clinic_id, "bot-1") is None

    await accounts.set_bot_token(env.clinic_id, "bot-1", "  123456:synthetic-token-value  ")

    stored = await env.scalar("SELECT bot_token_enc FROM agent.accounts WHERE id = 'bot-1'")
    assert stored
    assert "synthetic-token-value" not in stored
    assert await accounts.get_bot_token(env.clinic_id, "bot-1") == "123456:synthetic-token-value"
    fetched = await accounts.get_account(env.clinic_id, "bot-1")
    assert fetched is not None
    assert fetched.has_bot_token is True
    assert "synthetic-token-value" not in fetched.model_dump_json()

    await accounts.set_bot_token(env.clinic_id, "bot-1", "   ")
    assert await accounts.get_bot_token(env.clinic_id, "bot-1") is None
    fetched = await accounts.get_account(env.clinic_id, "bot-1")
    assert fetched is not None
    assert fetched.has_bot_token is False


@pytest.mark.usefixtures("secret_key")
async def test_credential_round_trip_and_a_wrong_key_reads_as_none(
    env: ClinicEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(thêm) credential Zalo mã hóa; đổi khóa thì giải mã hỏng -> None (có log riêng), không ném"""
    accounts = AccountStoreImpl(env.db)
    await _new_account(accounts, env, "acc-cred")
    await accounts.set_credential(env.clinic_id, "acc-cred", '{"cookie":"synthetic"}')
    assert await accounts.get_credential(env.clinic_id, "acc-cred") == '{"cookie":"synthetic"}'

    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "d" * 64)
    env_module.get_settings.cache_clear()
    assert await accounts.get_credential(env.clinic_id, "acc-cred") is None

    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "c" * 64)
    env_module.get_settings.cache_clear()
    await accounts.set_credential(env.clinic_id, "acc-cred", None)
    assert await accounts.get_credential(env.clinic_id, "acc-cred") is None


async def test_list_agents_reports_the_account_count_default_first(env: ClinicEnv) -> None:
    """(thêm) listAgents: số account dùng từng agent, agent mặc định đứng đầu"""
    agents, accounts = AgentStoreImpl(env.db), AccountStoreImpl(env.db)
    await agents.create_agent(env.clinic_id, agent_id="aa-tu-van", name="Tư Vấn", icon="💼", persona="")
    await _new_account(accounts, env, "acc-1", agent_id="aa-tu-van")
    await _new_account(accounts, env, "acc-2", agent_id="aa-tu-van")
    await _new_account(accounts, env, "acc-3")

    listed = await agents.list_agents_with_account_counts(env.clinic_id)
    assert [(a.id, count) for a, count in listed] == [(DEFAULT_AGENT_ID, 1), ("aa-tu-van", 2)]
