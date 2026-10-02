# ported from: src/config/agent-store.ts
"""Não của bot: persona + model override. Gắn vào account qua ``accounts.agent_id`` (table ``agent.agents``).

``AgentProfile`` itself is in ``pema_contracts.agents``.

Forced deviations:

* SQLite sync -> SQLAlchemy async + Postgres (``clinic_id``, no RLS); the primary key is ``(clinic_id, id)``
  and ``accounts`` has a REAL foreign key to the agent, so deleting an agent that an account uses is also
  refused by the database (the explicit check stays for its message);
* the original deleted the agent's Knowledge-Base and MCP bindings by hand in the same transaction
  (``xoaGanNguonCuaAgent`` / ``xoaGanServerCuaAgent``: agent ids are deterministic slugs, so deleting and
  re-creating the same name gives the same id and would inherit the old agent's documents). Here
  ``agent_kb_document`` and ``agent_mcp_servers`` reference the agent with ``ON DELETE CASCADE``, so the
  same guarantee is the database's and cannot be forgotten by a new caller;
* ``policy_profile`` is new (CONTRACTS-AI01 decision 2): the default is ``patient_channel`` (fail safe), and
  ``effective_policy_profile`` combines it with the account's, the RESTRICTIVE one winning.
* the unique partial index ``agents_one_default_idx`` makes "exactly one default agent" a database fact; the
  creation of the default agent runs under a transaction-scoped advisory lock so two processes starting
  together cannot both try.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.config.parse_disabled_tools import parse_disabled_tools
from pema.core.db import ClinicDatabase
from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.policy import PolicyProfileKey, effective_profile_key

DEFAULT_AGENT_ID = "tro-ly-mac-dinh"

_COLUMNS = (
    "id, icon, name, persona, model_provider, model_name, max_steps, reasoning_effort, "
    "disabled_tools, context_window, is_default, policy_profile"
)

_GET_DEFAULT = text(
    f"SELECT {_COLUMNS} FROM agent.agents WHERE clinic_id = :clinic_id AND is_default LIMIT 1"  # noqa: S608
)
_GET = text(f"SELECT {_COLUMNS} FROM agent.agents WHERE clinic_id = :clinic_id AND id = :id")  # noqa: S608
_LIST = text(
    f"""
    SELECT {_COLUMNS}, (SELECT COUNT(*) FROM agent.accounts a WHERE a.clinic_id = agents.clinic_id AND
    a.agent_id = agents.id) AS account_count FROM agent.agents WHERE clinic_id = :clinic_id ORDER BY
    is_default DESC, id
    """  # noqa: S608
)
_LOCK = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
_INSERT_DEFAULT = text(
    """
    INSERT INTO agent.agents (clinic_id, id, icon, name, persona, is_default)
    VALUES (:clinic_id, :id, '🤖', :name, '', true)
    ON CONFLICT (clinic_id, id) DO NOTHING
    """
)
_MARK_DEFAULT = text("UPDATE agent.agents SET is_default = true WHERE clinic_id = :clinic_id AND id = :id")
_INSERT = text(
    """
    INSERT INTO agent.agents (clinic_id, id, icon, name, persona, policy_profile)
    VALUES (:clinic_id, :id, :icon, :name, :persona, :policy_profile)
    """
)
_UPDATE = text(
    """
    UPDATE agent.agents SET icon = :icon, name = :name, persona = :persona, model_provider = :model_provider,
           model_name = :model_name, max_steps = :max_steps, reasoning_effort = :reasoning_effort,
           disabled_tools = CAST(:disabled_tools AS jsonb), context_window = :context_window,
           policy_profile = :policy_profile
    WHERE clinic_id = :clinic_id AND id = :id
    """
)
_COUNT_ACCOUNTS = text("SELECT COUNT(*) FROM agent.accounts WHERE clinic_id = :clinic_id AND agent_id = :id")
_DELETE = text("DELETE FROM agent.agents WHERE clinic_id = :clinic_id AND id = :id")

_PATCHABLE = frozenset(
    {
        "icon",
        "name",
        "persona",
        "model_provider",
        "model_name",
        "max_steps",
        "reasoning_effort",
        "disabled_tools",
        "context_window",
        "policy_profile",
    }
)


def to_profile(clinic_id: UUID, row: Any) -> AgentProfile:
    return AgentProfile(
        id=row["id"],
        clinic_id=clinic_id,
        icon=row["icon"],
        name=row["name"],
        persona=row["persona"],
        model_provider=row["model_provider"],
        model_name=row["model_name"],
        max_steps=row["max_steps"],
        reasoning_effort=row["reasoning_effort"],
        disabled_tools=parse_disabled_tools(row["disabled_tools"]),
        context_window=row["context_window"],
        is_default=bool(row["is_default"]),
        policy_profile=PolicyProfileKey(row["policy_profile"]),
    )


class AgentStoreImpl:
    """``AgentStore`` of ``pema_contracts.agents`` on ``agent.agents``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def ensure_default_agent(self, clinic_id: UUID) -> AgentProfile:
        """Agent mặc định luôn tồn tại - account mới/agent bị xóa đều rơi về đây."""
        async with self._db.session() as session:
            await session.execute(_LOCK, {"key": f"default-agent:{clinic_id}"})
            existing = (await session.execute(_GET_DEFAULT, {"clinic_id": clinic_id})).mappings().first()
            if existing is not None:
                return to_profile(clinic_id, existing)

            await session.execute(
                _INSERT_DEFAULT, {"clinic_id": clinic_id, "id": DEFAULT_AGENT_ID, "name": "Trợ lý mặc định"}
            )
            await session.execute(_MARK_DEFAULT, {"clinic_id": clinic_id, "id": DEFAULT_AGENT_ID})
            created = (
                (await session.execute(_GET, {"clinic_id": clinic_id, "id": DEFAULT_AGENT_ID}))
                .mappings()
                .one()
            )
        return to_profile(clinic_id, created)

    async def get_agent(self, clinic_id: UUID, agent_id: str) -> AgentProfile | None:
        async with self._db.session() as session:
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "id": agent_id})).mappings().first()
        return to_profile(clinic_id, row) if row is not None else None

    async def get_agent_for_account(self, clinic_id: UUID, account: AccountConfig) -> AgentProfile:
        """Agent của account - account trỏ agent đã bị xóa thì rơi về agent mặc định. (The foreign key makes a
        dangling reference impossible in Postgres; the fallback is kept as the original's safety net.)"""
        return await self.get_agent(clinic_id, account.agent_id) or await self.ensure_default_agent(clinic_id)

    async def get_effective_policy_profile(self, clinic_id: UUID, account: AccountConfig) -> PolicyProfileKey:
        """The profile a turn of ``account`` runs under: account and agent combined, the stricter wins."""
        agent = await self.get_agent_for_account(clinic_id, account)
        return effective_profile_key(account.policy_profile, agent.policy_profile)

    async def list_agents(self, clinic_id: UUID) -> list[AgentProfile]:
        return [agent for agent, _ in await self.list_agents_with_account_counts(clinic_id)]

    async def list_agents_with_account_counts(self, clinic_id: UUID) -> list[tuple[AgentProfile, int]]:
        """``listAgents``: every agent with the number of accounts that use it (default first, then by id)."""
        async with self._db.session() as session:
            rows = (await session.execute(_LIST, {"clinic_id": clinic_id})).mappings().all()
        return [(to_profile(clinic_id, r), int(r["account_count"])) for r in rows]

    async def create_agent(
        self,
        clinic_id: UUID,
        *,
        agent_id: str,
        name: str,
        icon: str,
        persona: str,
        policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL,
    ) -> AgentProfile:
        async with self._db.session() as session:
            await session.execute(
                _INSERT,
                {
                    "clinic_id": clinic_id,
                    "id": agent_id,
                    "icon": icon or "🤖",
                    "name": name,
                    "persona": persona,
                    "policy_profile": policy_profile.value,
                },
            )
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "id": agent_id})).mappings().one()
        return to_profile(clinic_id, row)

    async def update_agent(
        self, clinic_id: UUID, agent_id: str, patch: dict[str, object]
    ) -> AgentProfile | None:
        """A key that is PRESENT is written (``None`` clears a nullable field: ``model_provider``,
        ``model_name``, ``max_steps``, ``reasoning_effort``, ``context_window``); an ABSENT key keeps the
        stored value. This is the original's "drop the keys whose value is ``undefined`` before merging",
        expressed with the ``dict`` contract. Keys outside the patchable set (``id``, ``is_default``,
        ``clinic_id``) are rejected: silently ignoring them would answer with the OLD value as if saved."""
        unknown = set(patch) - _PATCHABLE
        if unknown:
            raise ValueError(f"update_agent: không được sửa các trường {sorted(unknown)}")

        async with self._db.session() as session:
            current_row = (
                (await session.execute(_GET, {"clinic_id": clinic_id, "id": agent_id})).mappings().first()
            )
            if current_row is None:
                return None
            merged = to_profile(clinic_id, current_row).model_dump() | patch
            validated = AgentProfile.model_validate(merged)
            await session.execute(
                _UPDATE,
                {
                    "clinic_id": clinic_id,
                    "id": agent_id,
                    "icon": validated.icon,
                    "name": validated.name,
                    "persona": validated.persona,
                    "model_provider": validated.model_provider.value if validated.model_provider else None,
                    "model_name": validated.model_name,
                    "max_steps": validated.max_steps,
                    "reasoning_effort": validated.reasoning_effort.value
                    if validated.reasoning_effort
                    else None,
                    "disabled_tools": json.dumps(validated.disabled_tools),
                    "context_window": validated.context_window,
                    "policy_profile": validated.policy_profile.value,
                },
            )
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "id": agent_id})).mappings().one()
        return to_profile(clinic_id, row)

    async def delete_agent(self, clinic_id: UUID, agent_id: str) -> tuple[bool, str | None]:
        """Không xóa được agent mặc định hoặc agent đang có account dùng. ``(ok, reason)``."""
        async with self._db.session() as session:
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "id": agent_id})).mappings().first()
            if row is None:
                return False, "Agent không tồn tại"
            if row["is_default"]:
                return False, "Không xóa được agent mặc định"

            used = int(
                (
                    await session.execute(_COUNT_ACCOUNTS, {"clinic_id": clinic_id, "id": agent_id})
                ).scalar_one()
            )
            if used > 0:
                return False, f"Đang có {used} account dùng agent này"

            # Dọn luôn gán Kho tri thức và gán server MCP: ``ON DELETE CASCADE`` (see module docstring).
            await session.execute(_DELETE, {"clinic_id": clinic_id, "id": agent_id})
        return True, None
