"""Account and agent configuration DTOs (tables ``agent.accounts`` and ``agent.agents``).

Port of ``AccountConfig`` (src/config/account-store.ts) and ``AgentProfile`` (src/config/agent-store.ts).
The brain is the agent (persona + model override); an account is a channel login that points to an
agent. N accounts may share one agent. Secrets (bot token, Zalo credential) are write-only and never
appear in a DTO: only ``has_bot_token`` does.

Deviations from zalo-agent: ``loai`` ("ca_nhan" | "bot") becomes ``channel`` (``ChannelKind``;
``ca_nhan`` = ``zalo_personal``, ``bot`` = ``zalo_bot``); ``policy_profile`` and ``clinic_id`` are new.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.channel import ChannelKind
from pema_contracts.common import ApiModel
from pema_contracts.policy import PolicyProfileKey


class LlmProviderKind(StrEnum):
    """``LLM_PROVIDER_KINDS`` of src/config/llm-provider-kind.ts."""

    OPENAI_COMPATIBLE = "openai-compatible"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class ReasoningEffort(StrEnum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class AllowlistMode(StrEnum):
    ALL = "all"
    LIST = "list"


class Allowlist(ApiModel):
    mode: AllowlistMode = AllowlistMode.ALL
    user_ids: list[str] = Field(default_factory=list[str])


class AccountConfig(ApiModel):
    id: str
    clinic_id: UUID
    label: str
    channel: ChannelKind
    has_bot_token: bool = Field(
        default=False, description="Bot accounts only. The token itself is never returned."
    )
    enabled: bool = True
    agent_id: str
    allowlist: Allowlist = Field(default_factory=Allowlist)
    group_require_mention: bool = True
    respond_to_groups: bool = True
    group_passive_listen: bool = True
    auto_react_enabled: bool = True
    auto_react_icon: str = "heart"
    typing_indicator_enabled: bool = True
    disabled_tools: list[str] = Field(
        default_factory=list[str],
        description="Tool keys switched OFF (deny list, so a newly added tool is on for old accounts).",
    )
    auto_accept_friends: bool = False
    auto_accept_friend_delay_minutes: int = Field(default=1, ge=0, le=1440)
    policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL


class AgentProfile(ApiModel):
    id: str
    clinic_id: UUID
    icon: str = "🤖"
    name: str
    persona: str = ""
    model_provider: LlmProviderKind | None = Field(
        default=None, description="None = use the shared provider configuration."
    )
    model_name: str | None = None
    max_steps: int | None = Field(default=None, ge=1)
    reasoning_effort: ReasoningEffort | None = None
    disabled_tools: list[str] = Field(default_factory=list[str])
    context_window: int | None = Field(default=None, ge=1000, description="Token budget for model input.")
    is_default: bool = False
    policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL


class AccountStore(Protocol):
    """Port of ``account-store.ts`` over ``agent.accounts``. Implemented by package D2; read by C1, C2, S, D1,
    D4 and the admin API. ``AccountConfig`` never carries a secret: the two ``get_*`` secret methods are the
    ONE easy-to-audit path that returns plaintext (``layBotTokenGiaiMa``), used only by the channel code."""

    async def get_account(self, clinic_id: UUID, account_id: str) -> AccountConfig | None: ...

    async def list_accounts(self, clinic_id: UUID) -> list[AccountConfig]: ...

    async def list_all_enabled_accounts(self) -> list[AccountConfig]:
        """Across clinics (a system query for process start-up; the implementation iterates clinics)."""
        ...

    async def create_account(
        self, clinic_id: UUID, *, account_id: str, label: str, channel: ChannelKind, agent_id: str | None
    ) -> AccountConfig: ...

    async def update_account(
        self, clinic_id: UUID, account_id: str, patch: dict[str, object]
    ) -> AccountConfig | None: ...

    async def delete_account(self, clinic_id: UUID, account_id: str) -> bool: ...

    async def get_bot_token(self, clinic_id: UUID, account_id: str) -> str | None:
        """Decrypted Zalo Bot API token. Never log it, never return it from the API."""
        ...

    async def set_bot_token(self, clinic_id: UUID, account_id: str, token: str) -> None: ...

    async def get_credential(self, clinic_id: UUID, account_id: str) -> str | None:
        """Decrypted Zalo personal credential (cookie JSON). Passed to the bridge, never stored in a file."""
        ...

    async def set_credential(self, clinic_id: UUID, account_id: str, credential: str | None) -> None: ...


class AgentStore(Protocol):
    """Port of ``agent-store.ts`` over ``agent.agents``. Implemented by package D2."""

    async def get_agent(self, clinic_id: UUID, agent_id: str) -> AgentProfile | None: ...

    async def get_agent_for_account(self, clinic_id: UUID, account: AccountConfig) -> AgentProfile:
        """The agent of an account, or the default one when the reference dangles (``getAgentForAccount``)."""
        ...

    async def ensure_default_agent(self, clinic_id: UUID) -> AgentProfile: ...

    async def list_agents(self, clinic_id: UUID) -> list[AgentProfile]: ...

    async def create_agent(
        self, clinic_id: UUID, *, agent_id: str, name: str, icon: str, persona: str
    ) -> AgentProfile: ...

    async def update_agent(
        self, clinic_id: UUID, agent_id: str, patch: dict[str, object]
    ) -> AgentProfile | None: ...

    async def delete_agent(self, clinic_id: UUID, agent_id: str) -> tuple[bool, str | None]:
        """``(ok, reason)``: refused while an account uses it; also clears its KB and MCP bindings."""
        ...
