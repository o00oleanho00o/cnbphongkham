# ported from: src/config/account-store.ts
"""Tài khoản kênh (table ``agent.accounts``). Não nằm ở agent, trỏ qua ``agent_id``.

``AccountConfig`` and ``ChannelKind`` are in ``pema_contracts`` (``loai: "ca_nhan" | "bot"`` became
``channel``: ``ca_nhan`` = ``zalo_personal``, ``bot`` = ``zalo_bot``, plus the ``zalo_oa`` stub).

Forced deviations:

* SQLite sync -> SQLAlchemy async + Postgres (``clinic_id`` = the fixed installation id, primary key
  ``(clinic_id, id)``; one installation is one clinic, there is no row level security);
* ``trongGiaoDich`` becomes the transaction of ``ClinicDatabase.session``;
* ``AccountStore.get_bot_token`` / ``get_credential`` are the ONE easy-to-audit path that returns a
  plaintext secret (``layBotTokenGiaiMa``); ``AccountConfig`` carries ``has_bot_token`` only, because the
  object goes out through ``GET /admin/accounts``;
* the ``channel`` is fixed at creation (the original: "`loai` chốt lúc tạo": three layers guarded the UPDATE
  and the only gap was delete-then-recreate with the same id, which is closed by deleting the jobs and
  friend requests below). ``datLoaiKenh`` is not ported: the contract has no way to change it, the stored
  credential means something different per channel;
* ``list_all_enabled_accounts`` (start-up of the listeners) is ONE query: the database holds one clinic
  (single tenant), so there is no loop over clinics any more;
* ``policy_profile`` is new: the default is ``patient_channel`` (fail safe, CONTRACTS-AI01 decision 2).
  ``AgentStoreImpl.get_effective_policy_profile`` combines it with the agent's, the restrictive one winning;
* secrets are encrypted with ``pema.config.secret_cipher`` (AES-GCM, key ``PEMA_SECRET_ENCRYPTION_KEY``),
  and never logged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pema.config.accounts import read_accounts_seed_file
from pema.config.agent_store import AgentStoreImpl
from pema.config.parse_disabled_tools import parse_disabled_tools
from pema.config.secret_cipher import decrypt_secret, encrypt_secret
from pema.conversation.sql_util import affected_rows
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig, Allowlist, AllowlistMode
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey

_log = create_logger("account-store")

_SELECT = """
    SELECT id, label, channel, enabled, agent_id, allowlist_mode, allowlist_user_ids,
           group_require_mention, respond_to_groups, group_passive_listen,
           auto_react_enabled, auto_react_icon, typing_indicator_enabled,
           disabled_tools, auto_accept_friends, auto_accept_friend_delay_minutes,
           policy_profile, (bot_token_enc <> '') AS has_bot_token
    FROM agent.accounts
"""
_LIST = text(_SELECT + " WHERE clinic_id = :clinic_id ORDER BY id")
_LIST_ENABLED = text(_SELECT + " WHERE enabled ORDER BY id")
_GET = text(_SELECT + " WHERE clinic_id = :clinic_id AND id = :id")
_INSERT = text(
    "INSERT INTO agent.accounts (clinic_id, id, label, channel, agent_id, policy_profile) "
    "VALUES (:clinic_id, :id, :label, :channel, :agent_id, :policy_profile)"
)
_UPDATE = text(
    """
    UPDATE agent.accounts SET label = :label, enabled = :enabled, agent_id = :agent_id,
           allowlist_mode = :allowlist_mode, allowlist_user_ids = CAST(:allowlist_user_ids AS jsonb),
           group_require_mention = :group_require_mention, respond_to_groups = :respond_to_groups,
           group_passive_listen = :group_passive_listen, auto_react_enabled = :auto_react_enabled,
           auto_react_icon = :auto_react_icon, typing_indicator_enabled = :typing_indicator_enabled,
           disabled_tools = CAST(:disabled_tools AS jsonb), auto_accept_friends = :auto_accept_friends,
           auto_accept_friend_delay_minutes = :auto_accept_friend_delay_minutes,
           policy_profile = :policy_profile
    WHERE clinic_id = :clinic_id AND id = :id
    """
)
# Dọn luôn lịch hẹn của account. Giờ ``agent.jobs`` KHÔNG có khóa ngoại tới accounts (như bản gốc), nên
# thiếu bước này thì job trở thành MỒ CÔI và sống dậy nếu ai đó tạo lại một account CÙNG ID - kể cả với loại
# kênh khác. (``job_runs`` đi theo job bằng ON DELETE CASCADE.)
_DELETE_JOBS = text("DELETE FROM agent.jobs WHERE clinic_id = :clinic_id AND account_id = :id")
# Dọn yêu cầu kết bạn đang chờ - cùng lý do MỒ CÔI như jobs: tạo lại account CÙNG ID mà auto-accept bật thì
# vòng quét accept những UID cũ rích.
_DELETE_FRIEND_REQUESTS = text(
    "DELETE FROM agent.friend_requests WHERE clinic_id = :clinic_id AND account_id = :id"
)
_DELETE = text("DELETE FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :id")
_COUNT = text("SELECT COUNT(*) FROM agent.accounts WHERE clinic_id = :clinic_id")
_INSERT_SEED = text(
    """
    INSERT INTO agent.accounts (clinic_id, id, label, enabled, agent_id, allowlist_mode, allowlist_user_ids,
        group_require_mention, respond_to_groups, group_passive_listen, policy_profile)
    VALUES (:clinic_id, :id, :label, :enabled, :agent_id, :allowlist_mode, CAST(:allowlist_user_ids AS jsonb),
        :group_require_mention, :respond_to_groups, :group_passive_listen, :policy_profile)
    """
)
_GET_BOT_TOKEN = text("SELECT bot_token_enc FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :id")
_SET_BOT_TOKEN = text(
    "UPDATE agent.accounts SET bot_token_enc = :enc WHERE clinic_id = :clinic_id AND id = :id"
)
_GET_CREDENTIAL = text("SELECT credential_enc FROM agent.accounts WHERE clinic_id = :clinic_id AND id = :id")
_SET_CREDENTIAL = text(
    "UPDATE agent.accounts SET credential_enc = :enc WHERE clinic_id = :clinic_id AND id = :id"
)
_AGENT_EXISTS = text("SELECT 1 FROM agent.agents WHERE clinic_id = :clinic_id AND id = :id")

# KHÔNG nhận ``channel`` và ``has_bot_token`` (và ``id``, ``clinic_id``): câu UPDATE không có các cột đó,
# nên nhận vào là nuốt lặng lẽ rồi trả về giá trị CŨ như thể đã lưu. Chặn tường minh thay vì để người gọi
# phát hiện bằng cách thấy dashboard không đổi gì. Đổi token đi qua ``set_bot_token``.
_PATCHABLE = frozenset(
    {
        "label",
        "enabled",
        "agent_id",
        "allowlist",
        "group_require_mention",
        "respond_to_groups",
        "group_passive_listen",
        "auto_react_enabled",
        "auto_react_icon",
        "typing_indicator_enabled",
        "disabled_tools",
        "auto_accept_friends",
        "auto_accept_friend_delay_minutes",
        "policy_profile",
    }
)


def _to_config(clinic_id: UUID, row: Any) -> AccountConfig:
    return AccountConfig(
        id=row["id"],
        clinic_id=clinic_id,
        label=row["label"],
        # Giá trị lạ trong cột không thể có (CHECK constraint); the original fell back to "ca_nhan".
        channel=ChannelKind(row["channel"]),
        has_bot_token=bool(row["has_bot_token"]),
        enabled=bool(row["enabled"]),
        agent_id=row["agent_id"],
        allowlist=Allowlist(
            # same defensive read as ``disabled_tools``: a JSON array of strings, anything else is empty
            mode=AllowlistMode(row["allowlist_mode"]),
            user_ids=parse_disabled_tools(row["allowlist_user_ids"]),
        ),
        group_require_mention=bool(row["group_require_mention"]),
        respond_to_groups=bool(row["respond_to_groups"]),
        group_passive_listen=bool(row["group_passive_listen"]),
        auto_react_enabled=bool(row["auto_react_enabled"]),
        auto_react_icon=row["auto_react_icon"],
        typing_indicator_enabled=bool(row["typing_indicator_enabled"]),
        disabled_tools=parse_disabled_tools(row["disabled_tools"]),
        auto_accept_friends=bool(row["auto_accept_friends"]),
        auto_accept_friend_delay_minutes=int(row["auto_accept_friend_delay_minutes"]),
        policy_profile=PolicyProfileKey(row["policy_profile"]),
    )


class AccountStoreImpl:
    """``AccountStore`` of ``pema_contracts.agents`` on ``agent.accounts``."""

    def __init__(self, db: ClinicDatabase, agents: AgentStoreImpl | None = None) -> None:
        self._db = db
        self._agents = agents or AgentStoreImpl(db)

    async def list_accounts(self, clinic_id: UUID) -> list[AccountConfig]:
        async with self._db.session() as session:
            rows = (await session.execute(_LIST, {"clinic_id": clinic_id})).mappings().all()
        return [_to_config(clinic_id, r) for r in rows]

    async def list_enabled_accounts(self, clinic_id: UUID) -> list[AccountConfig]:
        return [a for a in await self.list_accounts(clinic_id) if a.enabled]

    async def list_all_enabled_accounts(self) -> list[AccountConfig]:
        """Every enabled account of the installation (start-up of the listeners): one query."""
        clinic_id = await get_installation_clinic_id(self._db)
        async with self._db.session() as session:
            rows = (await session.execute(_LIST_ENABLED)).mappings().all()
        return [_to_config(clinic_id, r) for r in rows]

    async def get_account(self, clinic_id: UUID, account_id: str) -> AccountConfig | None:
        async with self._db.session() as session:
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "id": account_id})).mappings().first()
        return _to_config(clinic_id, row) if row is not None else None

    async def create_account(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        label: str,
        channel: ChannelKind,
        agent_id: str | None,
        policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL,
    ) -> AccountConfig:
        resolved_agent_id = await self._resolve_agent_id(clinic_id, agent_id)
        try:
            async with self._db.session() as session:
                await session.execute(
                    _INSERT,
                    {
                        "clinic_id": clinic_id,
                        "id": account_id,
                        "label": label,
                        "channel": channel.value,
                        "agent_id": resolved_agent_id,
                        "policy_profile": policy_profile.value,
                    },
                )
        except IntegrityError as err:
            raise DomainError(ErrorCode.INVALID_STATE, "Account id đã tồn tại.") from err
        created = await self.get_account(clinic_id, account_id)
        if created is None:  # cannot happen: the insert committed
            raise DomainError(ErrorCode.INTERNAL, "Không đọc lại được account vừa tạo.")
        return created

    async def update_account(
        self, clinic_id: UUID, account_id: str, patch: dict[str, object]
    ) -> AccountConfig | None:
        unknown = set(patch) - _PATCHABLE
        if unknown:
            raise ValueError(f"update_account: không được sửa các trường {sorted(unknown)}")

        current = await self.get_account(clinic_id, account_id)
        if current is None:
            return None
        merged = AccountConfig.model_validate(current.model_dump() | patch)
        if "agent_id" in patch and await self._agents.get_agent(clinic_id, merged.agent_id) is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Agent không tồn tại.")

        async with self._db.session() as session:
            await session.execute(
                _UPDATE,
                {
                    "clinic_id": clinic_id,
                    "id": account_id,
                    "label": merged.label,
                    "enabled": merged.enabled,
                    "agent_id": merged.agent_id,
                    "allowlist_mode": merged.allowlist.mode.value,
                    "allowlist_user_ids": json.dumps(merged.allowlist.user_ids),
                    "group_require_mention": merged.group_require_mention,
                    "respond_to_groups": merged.respond_to_groups,
                    "group_passive_listen": merged.group_passive_listen,
                    "auto_react_enabled": merged.auto_react_enabled,
                    "auto_react_icon": merged.auto_react_icon,
                    "typing_indicator_enabled": merged.typing_indicator_enabled,
                    "disabled_tools": json.dumps(merged.disabled_tools),
                    "auto_accept_friends": merged.auto_accept_friends,
                    "auto_accept_friend_delay_minutes": merged.auto_accept_friend_delay_minutes,
                    "policy_profile": merged.policy_profile.value,
                },
            )
        return await self.get_account(clinic_id, account_id)

    async def delete_account(self, clinic_id: UUID, account_id: str) -> bool:
        async with self._db.session() as session:
            params = {"clinic_id": clinic_id, "id": account_id}
            await session.execute(_DELETE_JOBS, params)
            await session.execute(_DELETE_FRIEND_REQUESTS, params)
            return affected_rows(await session.execute(_DELETE, params)) > 0

    async def run_accounts_seed_migration(self, clinic_id: UUID, config_path: Path | None = None) -> None:
        """Seed 1 lần từ config/accounts.json (bản cũ trước khi DB là source of truth). Account có persona
        riêng được tách thành agent riêng để giữ nguyên hành vi; persona rỗng dùng agent mặc định. Bảng
        accounts đã có dữ liệu thì bỏ qua. Runs for ONE clinic (the account table is per clinic)."""
        async with self._db.session() as session:
            count = int((await session.execute(_COUNT, {"clinic_id": clinic_id})).scalar_one())
        if count > 0:
            await self._agents.ensure_default_agent(clinic_id)
            return

        default_agent = await self._agents.ensure_default_agent(clinic_id)
        seed = read_accounts_seed_file(config_path)
        if not seed:
            return

        for acc in seed:
            agent_id = default_agent.id
            if acc.persona.strip():
                created = await self._agents.create_agent(
                    clinic_id,
                    agent_id=f"{acc.id}-agent",
                    name=f"Não của {acc.label}",
                    icon="🤖",
                    persona=acc.persona.strip(),
                    policy_profile=acc.policy_profile,
                )
                agent_id = created.id
            async with self._db.session() as session:
                await session.execute(
                    _INSERT_SEED,
                    {
                        "clinic_id": clinic_id,
                        "id": acc.id,
                        "label": acc.label,
                        "enabled": acc.enabled,
                        "agent_id": agent_id,
                        "allowlist_mode": acc.allowlist.mode,
                        "allowlist_user_ids": json.dumps(acc.allowlist.user_ids),
                        "group_require_mention": acc.group_require_mention,
                        "respond_to_groups": acc.respond_to_groups,
                        "group_passive_listen": acc.group_passive_listen,
                        "policy_profile": acc.policy_profile.value,
                    },
                )
        _log.info("Đã import accounts.json vào DB (chỉ chạy 1 lần)", imported=len(seed))

    # ----------------------------------------------------------------------------- secrets

    async def get_bot_token(self, clinic_id: UUID, account_id: str) -> str | None:
        """Token bot ĐÃ GIẢI MÃ. Đường riêng, KHÔNG đi qua ``AccountConfig`` - object đó được trả nguyên vẹn ở
        ``GET /admin/accounts``, nên token nằm trong đó là lộ bí mật cho mọi phiên dashboard đang mở. Tách ra
        thành một hàm để chỗ nào đọc token thật đều grep ra được ngay.

        Trả ``None`` khi: chưa nhập token, hoặc giải mã hỏng. Hai ca này caller đều xử lý như nhau (không chạy
        được kênh đó), nhưng ca giải mã hỏng có LOG riêng vì nó nghĩa là ``PEMA_SECRET_ENCRYPTION_KEY`` đã đổi
        so với lúc lưu - im lặng rơi về ``None`` ở đây thì người vận hành đi tìm nhầm chỗ.
        """
        return await self._read_secret(_GET_BOT_TOKEN, clinic_id, account_id, "token bot")

    async def set_bot_token(self, clinic_id: UUID, account_id: str, token: str) -> None:
        """Lưu token bot (mã hóa). Chuỗi rỗng = xóa token."""
        encrypted = encrypt_secret(token.strip()) if token.strip() else ""
        await self._write_secret(_SET_BOT_TOKEN, clinic_id, account_id, encrypted)

    async def get_credential(self, clinic_id: UUID, account_id: str) -> str | None:
        """Credential tài khoản Zalo cá nhân (cookie JSON), đã giải mã. Goes to the bridge, not to a file."""
        return await self._read_secret(_GET_CREDENTIAL, clinic_id, account_id, "credential Zalo")

    async def set_credential(self, clinic_id: UUID, account_id: str, credential: str | None) -> None:
        encrypted = encrypt_secret(credential) if credential else ""
        await self._write_secret(_SET_CREDENTIAL, clinic_id, account_id, encrypted)

    # ----------------------------------------------------------------------------- helpers

    async def _resolve_agent_id(self, clinic_id: UUID, agent_id: str | None) -> str:
        """``input.agentId && getAgent(...) ? input.agentId : ensureDefaultAgent().id``."""
        if agent_id and await self._agents.get_agent(clinic_id, agent_id) is not None:
            return agent_id
        return (await self._agents.ensure_default_agent(clinic_id)).id

    async def _read_secret(self, statement: Any, clinic_id: UUID, account_id: str, what: str) -> str | None:
        async with self._db.session() as session:
            stored = (await session.execute(statement, {"clinic_id": clinic_id, "id": account_id})).scalar()
        if not stored:
            return None
        try:
            return decrypt_secret(str(stored))
        except Exception as err:
            _log.error(
                "Không giải mã được bí mật của account - PEMA_SECRET_ENCRYPTION_KEY có đúng khóa không?",
                err=err,
                account_id=account_id,
                kind=what,
            )
            return None

    async def _write_secret(self, statement: Any, clinic_id: UUID, account_id: str, encrypted: str) -> None:
        async with self._db.session() as session:
            await session.execute(statement, {"clinic_id": clinic_id, "id": account_id, "enc": encrypted})
