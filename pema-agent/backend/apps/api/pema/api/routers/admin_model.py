# ported from: src/server/routes/provider-routes.ts, vision-routes.ts, tuning-routes.ts
"""LLM provider, vision sidecar and tuning parameters (package D1).

``image-routes.ts`` is in ``admin_tools.py`` (D4). API keys are write-only: responses carry ``api_key_masked``
only and every change is audited by field name, never by value.

Wiring that package G does (the dependencies below are the seams, so this file needs neither the session code
of package B1 nor a database): override ``provide_clinic_id`` (the clinic of the signed-in staff member, and
the permission check ``admin.model`` of the router that mounts this one) and ``provide_audit``
(``clinic.audit_log``); the runtime settings snapshot is installed at process start
(``install_runtime_settings``).

Deviations forced by the contract DTOs (``pema_contracts.admin_agent``):

* ``VisionSettingsOut`` has ``enabled`` / ``provider`` instead of the original ``mode`` + ``sidecar`` block.
  Mapping: ``enabled`` = image reading is available (the main model may read images, or a sidecar is
  configured); ``provider`` is the sidecar's (always OpenAI-compatible) or ``None``; the original ``mode`` is
  changed through ``enabled`` (False = ``off``, True = ``auto``). The three-way ``auto|on|off`` cannot be set
  from the FE until the contract grows a ``mode`` field (open item for package G).
* ``TuningItem.presets`` is a list of numbers: the label/hint of each quick-pick mark is not in the contract.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated
from uuid import UUID

from fastapi import Depends, status

from pema.agent.llm_provider import resolve_language_model
from pema.agent.model_vision_detection import clear_vision_detection_cache
from pema.agent.safe_turn_error import to_turn_error
from pema.agent.stream_text_result import chay_stream
from pema.api.deps import admin_router
from pema.config.runtime_llm_settings import (
    UNSET,
    clear_llm_settings,
    get_effective_llm_settings,
    mask_api_key,
    update_llm_settings,
)
from pema.config.runtime_llm_settings import (
    LlmSettingsUpdate as StoredLlmUpdate,
)
from pema.config.runtime_settings_store import get_runtime_settings
from pema.config.runtime_tuning_settings import (
    list_tuning,
    reset_tuning,
    set_tuning,
    validate_tuning,
)
from pema.config.runtime_vision_settings import (
    VisionSettings,
    clear_sidecar_settings,
    get_vision_settings,
    is_sidecar_configured,
    update_vision_settings,
)
from pema.config.runtime_vision_settings import (
    VisionSettingsUpdate as StoredVisionUpdate,
)
from pema.config.tuning_definitions import TUNING_DEFS, TUNING_GROUPS
from pema.config.tuning_specs import TUNING_SPECS, TuningValue
from pema.shared.current_datetime import is_valid_timezone
from pema.shared.logger import create_logger
from pema_contracts.admin_agent import (
    LlmSettingsOut,
    LlmSettingsUpdate,
    LlmTestResult,
    TuningGroup,
    TuningItem,
    TuningOut,
    TuningUpdate,
    VisionSettingsOut,
    VisionSettingsUpdate,
)
from pema_contracts.agents import LlmProviderKind
from pema_contracts.errors import DomainError, ErrorCode

log = create_logger("admin-model")

router = admin_router("model", "admin-model")

type AuditSink = Callable[[str, Sequence[str]], Awaitable[None]]
"""``(action, changed field names)``: NEVER a value (a key must not reach an audit row or a log)."""


async def provide_clinic_id() -> UUID:
    """The clinic of the signed-in staff member. Package G overrides it (``app.dependency_overrides``)."""
    raise DomainError(ErrorCode.NOT_IMPLEMENTED, "Chức năng chưa được nối với phiên đăng nhập.")


async def _log_audit(action: str, fields: Sequence[str]) -> None:
    log.info("dashboard change", action=action, changed_fields=list(fields))


async def provide_audit() -> AuditSink:
    """The audit sink. Default: the logger (field names only). Package G overrides it with ``audit_log``."""
    return _log_audit


ClinicId = Annotated[UUID, Depends(provide_clinic_id)]
Audit = Annotated[AuditSink, Depends(provide_audit)]

SIDECAR_KEYS = ("vision_mode", "vision_sidecar_base_url", "vision_sidecar_model", "vision_sidecar_api_key")


# ----------------------------------------------------------------------------------------------- provider


def _llm_out() -> LlmSettingsOut:
    s = get_effective_llm_settings()
    return LlmSettingsOut(
        provider=s.provider,
        base_url=s.base_url or "",
        model=s.model,
        # "never entered" and "entered but cannot be decrypted" look alike (no usable key) but are fixed in
        # different places
        api_key_masked="lỗi giải mã - nhập lại" if s.api_key_hong else mask_api_key(s.api_key),
        has_override=s.has_override,
    )


@router.get("/provider", response_model=LlmSettingsOut, summary="Effective LLM settings")
async def get_provider(clinic_id: ClinicId) -> LlmSettingsOut:
    return _llm_out()


@router.patch("/provider", response_model=LlmSettingsOut, summary="Change provider, base URL, model or key")
async def update_provider(body: LlmSettingsUpdate, clinic_id: ClinicId, audit: Audit) -> LlmSettingsOut:
    # An EMPTY field from the form means "not entered", NOT "a valid empty value": the page sends the whole
    # form on every save, so a field not filled in arrives as an empty string. Rejecting it would lose what
    # the user JUST typed in another field (the state of a fresh install: paste a base URL and a key, model
    # unknown, press Save -> the key just pasted would be lost).
    base_url = body.base_url
    if base_url is not None and base_url.strip() != "" and not base_url.startswith("http"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Base URL: phải bắt đầu bằng http")
    if body.model is not None and body.model.strip() == "" and body.model != "":
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Model: không được chỉ gồm khoảng trắng")
    update = StoredLlmUpdate(
        provider=body.provider,
        # None keeps, "" clears (the DTO's rule); the stored update says UNSET = keep, None = delete
        base_url=UNSET if base_url is None else (None if base_url.strip() == "" else base_url),
        model=body.model if body.model else None,
        api_key=body.api_key,
    )
    await update_llm_settings(clinic_id, update)
    changed = [
        name
        for name, value in (
            ("provider", body.provider),
            ("base_url", body.base_url),
            ("model", body.model),
            ("api_key", body.api_key),
        )
        if value not in (None, "")
    ]
    await audit("llm_settings.update", changed)
    return _llm_out()


@router.delete("/provider", response_model=LlmSettingsOut, summary="Drop the override, back to env config")
async def clear_provider(clinic_id: ClinicId, audit: Audit) -> LlmSettingsOut:
    await clear_llm_settings(clinic_id)
    await audit("llm_settings.clear", [])
    return _llm_out()


@router.post(
    "/provider/test", response_model=LlmTestResult, summary="Minimal completion with the effective config"
)
async def test_provider(clinic_id: ClinicId) -> LlmTestResult:
    """Call ONE minimal completion with the effective configuration: the "Test connection" button.

    It goes through the STREAMING path the bot uses: testing one way while the bot runs another shows a green
    button while the bot dies of a 524, or the opposite, exactly when someone presses it to find the cause.
    """
    try:
        result = await chay_stream(
            model=resolve_language_model(None),
            system="",
            messages=[{"role": "user", "content": "Trả lời đúng 1 từ: ok"}],
            max_output_tokens=200,
            max_retries=0,
            timeout_s=60,
        )
    except Exception as err:
        return LlmTestResult(ok=False, error=to_turn_error(err).safe_message)
    return LlmTestResult(ok=True, reply=result.text.strip()[:100])


# ------------------------------------------------------------------------------------------------ vision


def _vision_out() -> VisionSettingsOut:
    settings: VisionSettings = get_vision_settings()
    sidecar = settings.sidecar
    configured = is_sidecar_configured(settings)
    stored = get_runtime_settings()
    from pema.config.secret_cipher import mask_secret

    return VisionSettingsOut(
        enabled=settings.mode != "off" or configured,
        provider=LlmProviderKind.OPENAI_COMPATIBLE if configured else None,
        base_url=sidecar.base_url,
        model=sidecar.model,
        api_key_masked=mask_secret(sidecar.api_key),
        has_override=any(stored.read(key) is not None for key in SIDECAR_KEYS),
    )


@router.get("/vision", response_model=VisionSettingsOut, summary="Vision sidecar settings")
async def get_vision(clinic_id: ClinicId) -> VisionSettingsOut:
    return _vision_out()


@router.patch("/vision", response_model=VisionSettingsOut, summary="Change vision settings")
async def update_vision(body: VisionSettingsUpdate, clinic_id: ClinicId, audit: Audit) -> VisionSettingsOut:
    if body.provider not in (None, LlmProviderKind.OPENAI_COMPATIBLE):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "Sidecar đọc ảnh chỉ hỗ trợ endpoint tương thích OpenAI."
        )
    if body.base_url and not body.base_url.startswith("http"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Base URL: phải bắt đầu bằng http")
    await update_vision_settings(
        clinic_id,
        StoredVisionUpdate(
            mode=None if body.enabled is None else ("auto" if body.enabled else "off"),
            sidecar_base_url=body.base_url,
            sidecar_model=body.model,
            sidecar_api_key=body.api_key,
        ),
    )
    # A change must show at once, not wait for the /models cache to expire
    clear_vision_detection_cache()
    changed = [
        name
        for name, value in (
            ("enabled", body.enabled),
            ("provider", body.provider),
            ("base_url", body.base_url),
            ("model", body.model),
            ("api_key", body.api_key),
        )
        if value is not None
    ]
    await audit("vision_settings.update", changed)
    return _vision_out()


@router.delete(
    "/vision/sidecar", status_code=status.HTTP_204_NO_CONTENT, summary="Remove the sidecar override"
)
async def clear_vision_sidecar(clinic_id: ClinicId, audit: Audit) -> None:
    """Wipe the sidecar configuration, key included: the PATCH convention is "empty key = keep the old key",
    so there is no way to remove a key through PATCH."""
    await clear_sidecar_settings(clinic_id)
    clear_vision_detection_cache()
    await audit("vision_sidecar.clear", [])


# ------------------------------------------------------------------------------------------------ tuning

_KIND = {"number": "number", "boolean": "boolean", "enum": "select", "timezone": "text"}


def _tuning_out() -> TuningOut:
    current = {item.key: item for item in list_tuning()}
    items: list[TuningItem] = []
    for key, spec in TUNING_SPECS.items():
        definition = TUNING_DEFS[key]
        item = current[key]
        items.append(
            TuningItem(
                key=key,
                group=definition.group,
                label=definition.label,
                hint=definition.hint,
                kind=_KIND[spec.kind],  # type: ignore[arg-type]
                value=item.value,
                default=item.mac_dinh,
                overridden=not item.from_env,
                min=spec.minimum,
                max=spec.maximum,
                presets=None if definition.presets is None else [float(p.value) for p in definition.presets],
                options=list(spec.options) if spec.options else None,
                token_estimate_hint=definition.token_estimate_hint,
            )
        )
    return TuningOut(
        groups=[TuningGroup(id=g.id, title=g.title, hint=g.hint, nav_hint=g.nav_hint) for g in TUNING_GROUPS],
        items=items,
    )


@router.get(
    "/tuning",
    response_model=TuningOut,
    operation_id="admin_model_get_tuning",
    summary="Tuning parameters with effective values",
)
async def get_tuning_settings(clinic_id: ClinicId) -> TuningOut:
    return _tuning_out()


def _check_value(key: str, value: object) -> str | None:
    """The range/type/option check of ONE parameter (before the cross rules)."""
    spec = TUNING_SPECS[key]
    label = TUNING_DEFS[key].label
    if spec.kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            return f"{label}: phải là số"
        if (
            spec.minimum is not None
            and spec.maximum is not None
            and not spec.minimum <= value <= spec.maximum
        ):
            return f"{label}: phải trong khoảng {spec.minimum:g} - {spec.maximum:g}"
    elif spec.kind == "boolean":
        if not isinstance(value, bool):
            return f"{label}: phải là true hoặc false"
    elif spec.kind == "enum":
        if str(value) not in spec.options:
            return f"{label}: chỉ nhận {', '.join(spec.options)}"
    elif spec.kind == "timezone" and not is_valid_timezone(str(value)):
        # A broken zone slipping into the DB makes the scheduler fall back to UTC SILENTLY: reminders 7 hours
        # off with no error to point at the cause. Stopped at the door.
        return f'{label}: "{value}" không phải tên timezone IANA hợp lệ (vd Asia/Ho_Chi_Minh)'
    return None


@router.patch("/tuning", response_model=TuningOut, summary="Override tuning parameters (null removes)")
async def update_tuning(body: TuningUpdate, clinic_id: ClinicId, audit: Audit) -> TuningOut:
    values = body.values
    # Stop an unknown key: ``set_tuning`` writes straight to runtime_settings so an invented key would become
    # permanent garbage in the table
    unknown = [key for key in values if key not in TUNING_SPECS]
    if unknown:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"Không có tham số: {', '.join(unknown)}")

    # Check the range of EACH parameter first, then the cross rules
    errors = [
        message
        for key, value in values.items()
        if value is not None and (message := _check_value(key, value)) is not None
    ]
    if errors:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "\n".join(errors))

    # Constraints BETWEEN parameters: the user may edit one field only, so the check runs on the merged values
    merged: dict[str, TuningValue] = {key: value for key, value in values.items() if value is not None}
    cross = validate_tuning(merged)
    if cross:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "\n".join(cross))

    for key, value in values.items():
        await set_tuning(clinic_id, key, value)
    await audit("tuning.update", sorted(values))
    return _tuning_out()


@router.delete(
    "/tuning",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="admin_model_reset_tuning",
    summary="Remove every tuning override",
)
async def reset_tuning_settings(clinic_id: ClinicId, audit: Audit) -> None:
    await reset_tuning(clinic_id)
    await audit("tuning.reset", [])


__all__ = ["Audit", "AuditSink", "ClinicId", "provide_audit", "provide_clinic_id", "router"]
