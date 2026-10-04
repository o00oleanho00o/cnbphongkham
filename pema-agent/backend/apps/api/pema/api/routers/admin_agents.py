# ported from: src/server/routes/agent-routes.ts
"""Agents: persona, per-agent model, tools, context window (package D2 implements the store;
D1 owns the meaning of the fields). Port of src/server/routes/agent-routes.ts.

Forced deviations: Hono + zod become FastAPI + the ``pema_contracts.admin_agent`` DTOs (the request bodies are
validated by pydantic; the extra bounds of the original zod schema that the DTO does not carry are checked in
``_check_bounds``). Responses follow the OpenAPI skeleton (``AgentOut`` instead of ``{items}`` / ``{agent}``,
204 instead of ``{ok: true}``).

Security decision (new): a ``policy_profile`` that LOOSENS safety (anything -> ``staff_assistant``) needs the
``admin.policy`` permission on top of ``admin.agents``; tightening it needs nothing extra. The profile decides
what may leave the system towards a patient, so the person who edits personas must not be able to switch the
safety profile off just because they can edit an agent.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request, status

from pema.api.deps import admin_router
from pema.api.routers.admin_stores import (
    ClinicId,
    Stores,
    record_audit,
    require_permission,
)
from pema.config.runtime_tuning_settings import get_tuning_int
from pema_contracts.admin_agent import AgentCreate, AgentOut, AgentUpdate
from pema_contracts.agents import AgentProfile
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.roles import Permission
from pema_contracts.tools import BUILTIN_TOOL_KEYS, CLINIC_TOOL_KEYS

router = admin_router("agents", "admin-agents")

_VALID_TOOL_KEYS = frozenset((*BUILTIN_TOOL_KEYS, *CLINIC_TOOL_KEYS))
_MAX_STEPS_CEILING = 30
_CONTEXT_WINDOW_MIN = 4_000
_CONTEXT_WINDOW_MAX = 2_000_000


def _to_out(profile: AgentProfile, account_count: int) -> AgentOut:
    return AgentOut(**profile.model_dump(), account_count=account_count)


def _context_window_cross_check(window: int | None) -> str | None:
    """Trần ngữ cảnh riêng của agent phải lớn hơn hẳn trần token model được phép viết ra - cùng bất đẳng thức
    mà ``LUAT_CHEO`` áp cho cấu hình chung. ``None`` nghĩa là "theo cấu hình chung", không cần kiểm."""
    if window is None:
        return None
    max_output = get_tuning_int("LLM_MAX_OUTPUT_TOKENS")
    if window * 0.3 > max_output:
        return None
    return (
        f"Trần ngữ cảnh của agent ({window}) quá thấp so với trần token bot viết ra ({max_output}): bot chừa "
        "30% trần cho phần viết ra và cho kết quả công cụ, nên trần này phải lớn hơn khoảng 3,4 lần."
    )


def _check_bounds(patch: dict[str, object]) -> None:
    """The bounds of the original ``patchSchema`` that ``AgentUpdate`` does not carry."""
    max_steps = patch.get("max_steps")
    if isinstance(max_steps, int) and max_steps > _MAX_STEPS_CEILING:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"Số bước tối đa không được vượt {_MAX_STEPS_CEILING}."
        )

    window = patch.get("context_window")
    if isinstance(window, int):
        if not _CONTEXT_WINDOW_MIN <= window <= _CONTEXT_WINDOW_MAX:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"Trần ngữ cảnh phải nằm trong {_CONTEXT_WINDOW_MIN}..{_CONTEXT_WINDOW_MAX}.",
            )
        # Ràng buộc chéo GIỐNG trang Cấu hình. Ô ``context_window`` của agent đi đường này và trước đó không
        # có kiểm nào - tức là đường tài liệu KHUYÊN dùng ("agent chạy model khác đặt riêng được ở trang
        # Agents") lại là đường lách được luật. Ví dụ lọt qua trước đây: 4.000 với LLM_MAX_OUTPUT_TOKENS mặc
        # định 16.384 -> ngân sách ngữ cảnh còn 2.800 token trong khi model được phép viết ra 16.384.
        problem = _context_window_cross_check(window)
        if problem is not None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, problem)

    tools = patch.get("disabled_tools")
    if isinstance(tools, list):
        # Chặn key lạ ngay ở biên bằng chính danh mục tool: key rác lọt vào DB thì im lặng vô hại nhưng đọc
        # log lại tưởng tool đó tồn tại.
        keys = {str(t) for t in cast("list[object]", tools)}
        unknown = sorted(keys - _VALID_TOOL_KEYS)
        if unknown:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"Tool không tồn tại: {', '.join(unknown)}.")


@router.get("", response_model=list[AgentOut], summary="Agents with the number of accounts using each")
async def list_agents(clinic_id: ClinicId, stores: Stores) -> list[AgentOut]:
    await stores.agents.ensure_default_agent(clinic_id)  # UI luôn có ít nhất agent mặc định để gắn account
    return [_to_out(p, n) for p, n in await stores.agents.list_agents_with_account_counts(clinic_id)]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED, summary="Create an agent")
async def create_agent(request: Request, clinic_id: ClinicId, stores: Stores, body: AgentCreate) -> AgentOut:
    if body.policy_profile == PolicyProfileKey.STAFF_ASSISTANT:
        require_permission(request, Permission.ADMIN_POLICY)
    if await stores.agents.get_agent(clinic_id, body.id) is not None:
        raise DomainError(ErrorCode.INVALID_STATE, "Agent id đã tồn tại.")

    agent = await stores.agents.create_agent(
        clinic_id,
        agent_id=body.id,
        name=body.name,
        icon=body.icon,
        persona=body.persona,
        policy_profile=body.policy_profile,
    )
    await record_audit(
        stores, clinic_id, "agent.create", "agent", agent.id, {"policy_profile": agent.policy_profile.value}
    )
    return _to_out(agent, 0)


@router.patch(
    "/{agent_id}", response_model=AgentOut, summary="Update persona, model override, tools, profile"
)
async def update_agent(
    request: Request, agent_id: str, clinic_id: ClinicId, stores: Stores, body: AgentUpdate
) -> AgentOut:
    patch: dict[str, object] = body.model_dump(exclude_unset=True)
    if patch.pop("clear_model_override", False):
        # null = bỏ override, quay về cấu hình Providers chung.
        patch.update({"model_provider": None, "model_name": None, "max_steps": None})
    # An explicit null for a field that is not nullable would be a request to clear it: drop it.
    for required in ("name", "icon", "persona", "disabled_tools", "policy_profile"):
        if required in patch and patch[required] is None:
            del patch[required]
    _check_bounds(patch)

    current = await stores.agents.get_agent(clinic_id, agent_id)
    if current is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Agent không tồn tại.")
    loosens = (
        patch.get("policy_profile") == PolicyProfileKey.STAFF_ASSISTANT
        and current.policy_profile != PolicyProfileKey.STAFF_ASSISTANT
    )
    if loosens:
        require_permission(request, Permission.ADMIN_POLICY)

    agent = await stores.agents.update_agent(clinic_id, agent_id, patch)
    if agent is None:  # deleted between the read and the write
        raise DomainError(ErrorCode.NOT_FOUND, "Agent không tồn tại.")
    await record_audit(
        stores,
        clinic_id,
        "agent.update",
        "agent",
        agent_id,
        {"fields": sorted(patch), "loosens_policy": loosens},
    )
    counts = {p.id: n for p, n in await stores.agents.list_agents_with_account_counts(clinic_id)}
    return _to_out(agent, counts.get(agent.id, 0))


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent (refused while an account uses it; clears its KB and MCP bindings)",
)
async def delete_agent(agent_id: str, clinic_id: ClinicId, stores: Stores) -> None:
    ok, reason = await stores.agents.delete_agent(clinic_id, agent_id)
    if not ok:
        missing = reason == "Agent không tồn tại"
        raise DomainError(
            ErrorCode.NOT_FOUND if missing else ErrorCode.INVALID_STATE,
            reason or "Không xóa được agent.",
        )
    await record_audit(stores, clinic_id, "agent.delete", "agent", agent_id, {})
