"""LLM provider, vision sidecar and tuning parameters (package D1 implements).

Port of provider-routes.ts, vision-routes.ts and tuning-routes.ts.
image-routes.ts is in admin_tools.py (D4). API keys are
write-only: responses carry ``api_key_masked`` only and every change is audited by field name, never
by value.
"""

from __future__ import annotations

from fastapi import status

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import (
    LlmSettingsOut,
    LlmSettingsUpdate,
    LlmTestResult,
    TuningOut,
    TuningUpdate,
    VisionSettingsOut,
    VisionSettingsUpdate,
)

router = admin_router("model", "admin-model")


@router.get("/provider", response_model=LlmSettingsOut, summary="Effective LLM settings")
async def get_provider() -> LlmSettingsOut:
    not_implemented()


@router.patch("/provider", response_model=LlmSettingsOut, summary="Change provider, base URL, model or key")
async def update_provider(body: LlmSettingsUpdate) -> LlmSettingsOut:
    not_implemented()


@router.delete("/provider", response_model=LlmSettingsOut, summary="Drop the override, back to env config")
async def clear_provider() -> LlmSettingsOut:
    not_implemented()


@router.post(
    "/provider/test", response_model=LlmTestResult, summary="Minimal completion with the effective config"
)
async def test_provider() -> LlmTestResult:
    not_implemented()


@router.get("/vision", response_model=VisionSettingsOut, summary="Vision sidecar settings")
async def get_vision() -> VisionSettingsOut:
    not_implemented()


@router.patch("/vision", response_model=VisionSettingsOut, summary="Change vision settings")
async def update_vision(body: VisionSettingsUpdate) -> VisionSettingsOut:
    not_implemented()


@router.delete(
    "/vision/sidecar", status_code=status.HTTP_204_NO_CONTENT, summary="Remove the sidecar override"
)
async def clear_vision_sidecar() -> None:
    not_implemented()


@router.get("/tuning", response_model=TuningOut, summary="Tuning parameters with effective values")
async def get_tuning() -> TuningOut:
    not_implemented()


@router.patch("/tuning", response_model=TuningOut, summary="Override tuning parameters (null removes)")
async def update_tuning(body: TuningUpdate) -> TuningOut:
    not_implemented()


@router.delete("/tuning", status_code=status.HTTP_204_NO_CONTENT, summary="Remove every tuning override")
async def reset_tuning() -> None:
    not_implemented()
