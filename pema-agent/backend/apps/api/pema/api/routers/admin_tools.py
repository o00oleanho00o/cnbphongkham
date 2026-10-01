# ported from: src/server/routes/tool-routes.ts and src/server/routes/image-routes.ts
"""Tool catalogue, source-chain settings and image generation settings (package D4 implements).

``GET /admin/tools`` uses the SAME ``ToolRegistry.check_availability`` as the engine, so the page never
shows a tool as usable that the model did not receive. Per-account and per-agent switches are changed
through ``PATCH /admin/accounts/{id}`` and ``PATCH /admin/agents/{id}`` (``disabled_tools``).

Forced deviations (Hono + zod -> FastAPI + pydantic; global module state -> injected services):

* the routes read what they need from ``ToolsAdminServices`` (the registry, the account and agent stores,
  the static channel capabilities, the clinic of the request), installed by the composition root through
  ``install_tools_admin_services`` and overridable in tests with ``app.dependency_overrides``;
* the original answered ``400`` for an unknown ``agentId`` / ``accountId`` ("do not silently fall back to the
  personal channel"); the shared error vocabulary has ``validation_failed`` (HTTP 422) for that, same meaning;
* ``PATCH`` of the Brave key / image key is write-only: nothing here ever returns a secret, and the audit
  log line records WHICH fields changed, never a value (the original rule);
* ``POST /image-gen/test`` (draws a real picture to prove the model name) is not in the OpenAPI skeleton
  of package A, so it is not served here: open item for package G (it costs money, it needs a deliberate
  contract).

The role/permission check (RBAC) is package B1's dependency on the admin routers; it is not re-implemented
here."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Query, status

from pema.agent.tools.tool_deps import ToolDeps
from pema.api.deps import admin_router, not_implemented
from pema.config.runtime_image_settings import (
    ImageSettingsUpdate,
    clear_image_settings,
    get_image_settings_for_api,
    update_image_settings,
)
from pema.config.runtime_tool_settings import (
    FetchSettingsUpdate,
    SearchSettingsUpdate,
    get_fetch_settings_for_api,
    get_search_settings_for_api,
    update_fetch_settings,
    update_search_settings,
)
from pema.shared.logger import create_logger
from pema_contracts.admin_agent import (
    ImageGenSettingsOut,
    ImageGenSettingsUpdate,
    ToolChainSettings,
    ToolChainUpdate,
    ToolOut,
    ToolSourceStep,
)
from pema_contracts.agents import AccountConfig, AccountStore, AgentProfile, AgentStore
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import DEFAULT_PROFILES, PolicyProfileKey, effective_profile_key
from pema_contracts.tools import ToolRegistry, ToolScope

router = admin_router("tools", "admin-tools")
log = create_logger("tool-routes")

BRAVE_STEP_ID = "brave"
DUCKDUCKGO_STEP_ID = "duckduckgo"
SELF_FETCH_STEP_ID = "self"
JINA_STEP_ID = "jina"


class ChannelCapabilitiesProvider(Protocol):
    """Static capabilities of a channel KIND (package C1 for the Bot API, C2 for the personal channel).
    The Tools page needs them for an account that is not running, where there is no channel object to
    ask."""

    def capabilities_for(self, kind: ChannelKind) -> ChannelCapabilities: ...


@dataclass(frozen=True)
class ToolsAdminServices:
    registry: ToolRegistry
    accounts: AccountStore
    agents: AgentStore
    channels: ChannelCapabilitiesProvider
    clinic_id: Callable[[], UUID]
    """The clinic of the current request (from the session, package B1). A function so one object serves every
    request."""


_services: ToolsAdminServices | None = None


def install_tools_admin_services(services: ToolsAdminServices | None) -> None:
    """Called by the composition root (package G) at start-up; tests pass ``None`` to reset."""
    global _services
    _services = services


def get_tools_admin_services() -> ToolsAdminServices:
    if _services is None:
        not_implemented()
    return _services


Services = Annotated[ToolsAdminServices, Depends(get_tools_admin_services)]


def _bad_request(message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, message)


async def _build_scope(
    services: ToolsAdminServices, agent_id: str | None, account_id: str | None
) -> tuple[ToolScope, AccountConfig | None, AgentProfile | None]:
    """The scope for ``GET /admin/tools``.

    With a valid ``agent_id`` the REAL scope of that agent comes back, so ``kb_search.available`` answers
    "has THIS agent got a source": without this the agent edit page (where the source was just assigned)
    would still say "not usable". The ``account_id`` gives the channel of exactly the account being
    viewed; without it the Tools page of an account would show 15 usable tools and "Send file" would stay
    green while the model running on a Bot account does not receive it: the very class of bug the
    ``available`` flag exists to stop, only on the channel axis.

    An ``agent_id`` / ``account_id`` that does not exist is an ERROR, never a silent fallback to "no
    agent" / "personal channel": silently turning a wrong id into "unknown" sets a trap for the next
    debugging session, the numbers shown stay "plausible" but belong to the wrong context.

    A request with NO agent uses the EMPTY agent id as the deliberate convention "which agent is unknown":
    ``kb_search`` then asks "does the store have any source at all" instead of "sources of which agent".
    """
    clinic_id = services.clinic_id()
    account: AccountConfig | None = None
    if account_id:
        account = await services.accounts.get_account(clinic_id, account_id)
        if account is None:
            raise _bad_request("Account không tồn tại")
    agent: AgentProfile | None = None
    if agent_id:
        agent = await services.agents.get_agent(clinic_id, agent_id)
        if agent is None:
            raise _bad_request("Agent không tồn tại")
    kind = account.channel if account is not None else ChannelKind.ZALO_PERSONAL
    scope = ToolScope(
        agent_id=agent.id if agent is not None else "",
        agent_disabled_tools=agent.disabled_tools if agent is not None else [],
        account_disabled_tools=[],
        channel=services.channels.capabilities_for(kind),
        clinic_id=clinic_id,
    )
    return scope, account, agent


def _profile_disabled_keys(account: AccountConfig | None, agent: AgentProfile | None) -> frozenset[str]:
    """Keys switched off by the policy profile of the account and agent being viewed (the restrictive one
    wins). Nothing is viewed -> nothing is claimed blocked."""
    if account is None and agent is None:
        return frozenset()
    account_key = account.policy_profile if account is not None else PolicyProfileKey.STAFF_ASSISTANT
    agent_key = agent.policy_profile if agent is not None else PolicyProfileKey.STAFF_ASSISTANT
    return DEFAULT_PROFILES[effective_profile_key(account_key, agent_key)].disabled_tool_keys


@router.get(
    "", response_model=list[ToolOut], summary="Catalogue with availability for an account/agent scope"
)
async def list_tools(
    services: Services,
    agent_id: Annotated[str | None, Query(description="Scope availability to this agent.")] = None,
    account_id: Annotated[
        str | None, Query(description="Scope availability to this account's channel.")
    ] = None,
) -> list[ToolOut]:
    scope, account, agent = await _build_scope(services, agent_id, account_id)
    blocked = _profile_disabled_keys(account, agent)
    items: list[ToolOut] = []
    for spec in services.registry.definitions():
        # ``usable`` = is the infrastructure ready (unlike on/off per account). Without it the UI would
        # show a tool switched on while the model never receives it.
        availability = services.registry.check_availability(spec, scope)
        blocked_by_policy = spec.key in blocked
        usable = availability.usable and not blocked_by_policy
        hint = availability.hint
        if blocked_by_policy and availability.usable:
            hint = "Hồ sơ chính sách của kênh này tắt tool này (kênh bệnh nhân chỉ dùng chữ)"
        items.append(
            ToolOut(
                key=spec.key,
                label=spec.label,
                description=spec.description,
                group=spec.group.value,
                has_settings=spec.has_settings,
                usable=usable,
                hint=None if usable else hint,
                disabled_for_account=account is not None and spec.key in account.disabled_tools,
                disabled_for_agent=agent is not None and spec.key in agent.disabled_tools,
                blocked_by_policy=blocked_by_policy,
            )
        )
    return items


def _search_chain() -> ToolChainSettings:
    settings = get_search_settings_for_api()
    brave_on = settings.provider == "brave"
    return ToolChainSettings(
        steps=[
            ToolSourceStep(id=BRAVE_STEP_ID, label="Brave Search", enabled=brave_on),
            # The LAST step of each chain cannot be switched off: the tool never falls into "not configured":
            # web_search always keeps DuckDuckGo.
            ToolSourceStep(id=DUCKDUCKGO_STEP_ID, label="DuckDuckGo", enabled=True),
        ],
        brave_api_key_set=settings.has_brave_api_key,
    )


def _fetch_chain() -> ToolChainSettings:
    fallback = get_fetch_settings_for_api().fallback_enabled
    return ToolChainSettings(
        steps=[
            ToolSourceStep(id=SELF_FETCH_STEP_ID, label="Tự tải (chặn IP nội bộ)", enabled=True),
            ToolSourceStep(id=JINA_STEP_ID, label="Jina Reader", enabled=fallback),
        ],
        fallback_enabled=fallback,
    )


def _step_enabled(steps: Sequence[ToolSourceStep] | None, step_id: str) -> bool | None:
    for step in steps or ():
        if step.id == step_id:
            return step.enabled
    return None


@router.get("/web_search", response_model=ToolChainSettings, summary="web_search source chain")
async def get_web_search_settings(services: Services) -> ToolChainSettings:
    return _search_chain()


@router.patch("/web_search", response_model=ToolChainSettings, summary="Reorder or toggle search sources")
async def update_web_search_settings(body: ToolChainUpdate, services: Services) -> ToolChainSettings:
    if _step_enabled(body.steps, DUCKDUCKGO_STEP_ID) is False:
        raise _bad_request("Bậc cuối của chuỗi tìm kiếm (DuckDuckGo) không tắt được")
    brave_on = _step_enabled(body.steps, BRAVE_STEP_ID)
    provider = None if brave_on is None else ("brave" if brave_on else "duckduckgo")
    try:
        await update_search_settings(
            SearchSettingsUpdate(provider=provider, brave_api_key=body.brave_api_key)
        )
    except DomainError:
        # Choosing brave with no key: a user error, not a server error (the store raises the same vocabulary)
        raise
    # Audit: record WHICH field changed, NOT the value of the key
    log.info(
        "Đổi cấu hình web search từ dashboard",
        provider=provider,
        changed_key=body.brave_api_key is not None,
    )
    return _search_chain()


@router.get("/web_fetch", response_model=ToolChainSettings, summary="web_fetch extractor chain")
async def get_web_fetch_settings(services: Services) -> ToolChainSettings:
    return _fetch_chain()


@router.patch("/web_fetch", response_model=ToolChainSettings, summary="Toggle the fetch fallback")
async def update_web_fetch_settings(body: ToolChainUpdate, services: Services) -> ToolChainSettings:
    if _step_enabled(body.steps, SELF_FETCH_STEP_ID) is False:
        raise _bad_request("Bậc tự tải của web_fetch không tắt được")
    fallback = body.fallback_enabled
    if fallback is None:
        fallback = _step_enabled(body.steps, JINA_STEP_ID)
    settings = await update_fetch_settings(FetchSettingsUpdate(fallback_enabled=fallback))
    log.info("Đổi cấu hình web fetch từ dashboard", fallback_enabled=settings.fallback_enabled)
    return _fetch_chain()


def _image_out() -> ImageGenSettingsOut:
    view = get_image_settings_for_api()
    return ImageGenSettingsOut(
        enabled=view.configured,
        base_url=view.base_url,
        model=view.model,
        api_key_masked=view.api_key_masked,
        has_override=view.has_override,
    )


@router.get("/image-gen", response_model=ImageGenSettingsOut, summary="Image generation settings")
async def get_image_gen(services: Services) -> ImageGenSettingsOut:
    return _image_out()


@router.patch("/image-gen", response_model=ImageGenSettingsOut, summary="Change image generation settings")
async def update_image_gen(body: ImageGenSettingsUpdate, services: Services) -> ImageGenSettingsOut:
    # An empty string is explicit "delete" (back to the environment); anything else must be an http(s) URL
    if body.base_url and not body.base_url.startswith("http"):
        raise _bad_request("Base URL phải bắt đầu bằng http")
    # ``enabled`` has no stored meaning: the tool is usable exactly when base URL + model + key are all set
    # (``is_image_gen_configured``); the field only exists in the response.
    await update_image_settings(
        ImageSettingsUpdate(base_url=body.base_url, model=body.model, api_key=body.api_key)
    )
    # Audit: record which fields changed, not the values (so a key never reaches the log)
    changed = sorted(name for name in ("base_url", "model", "api_key") if getattr(body, name) is not None)
    log.info("Đổi cấu hình vẽ ảnh từ dashboard", changed_fields=changed)
    return _image_out()


@router.delete("/image-gen", status_code=status.HTTP_204_NO_CONTENT, summary="Drop the image-gen override")
async def clear_image_gen(services: Services) -> None:
    # Wipe everything INCLUDING the key: PATCH keeps the old key when the field is empty, so removing a
    # key needs its own action.
    await clear_image_settings()
    log.info("Xóa cấu hình vẽ ảnh từ dashboard")


def tools_deps_of(services: ToolsAdminServices) -> ToolDeps | None:  # pragma: no cover - typing helper
    """(Unused hook kept for package G: the registry already holds its deps.)"""
    return None
