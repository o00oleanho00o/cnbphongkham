"""Tool catalogue, source-chain settings and image generation settings (package D4 implements).

Port of tool-routes.ts and image-routes.ts.

``GET /admin/tools`` uses the SAME ``ToolRegistry.check_availability`` as the engine, so the page never
shows a tool as usable that the model did not receive. Per-account and per-agent switches are changed
through ``PATCH /admin/accounts/{id}`` and ``PATCH /admin/agents/{id}`` (``disabled_tools``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query, status

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import (
    ImageGenSettingsOut,
    ImageGenSettingsUpdate,
    ToolChainSettings,
    ToolChainUpdate,
    ToolOut,
)

router = admin_router("tools", "admin-tools")


@router.get(
    "", response_model=list[ToolOut], summary="Catalogue with availability for an account/agent scope"
)
async def list_tools(
    agent_id: Annotated[str | None, Query(description="Scope availability to this agent.")] = None,
    account_id: Annotated[
        str | None, Query(description="Scope availability to this account's channel.")
    ] = None,
) -> list[ToolOut]:
    not_implemented()


@router.get("/web_search", response_model=ToolChainSettings, summary="web_search source chain")
async def get_web_search_settings() -> ToolChainSettings:
    not_implemented()


@router.patch("/web_search", response_model=ToolChainSettings, summary="Reorder or toggle search sources")
async def update_web_search_settings(body: ToolChainUpdate) -> ToolChainSettings:
    not_implemented()


@router.get("/web_fetch", response_model=ToolChainSettings, summary="web_fetch extractor chain")
async def get_web_fetch_settings() -> ToolChainSettings:
    not_implemented()


@router.patch("/web_fetch", response_model=ToolChainSettings, summary="Toggle the fetch fallback")
async def update_web_fetch_settings(body: ToolChainUpdate) -> ToolChainSettings:
    not_implemented()


@router.get("/image-gen", response_model=ImageGenSettingsOut, summary="Image generation settings")
async def get_image_gen() -> ImageGenSettingsOut:
    not_implemented()


@router.patch("/image-gen", response_model=ImageGenSettingsOut, summary="Change image generation settings")
async def update_image_gen(body: ImageGenSettingsUpdate) -> ImageGenSettingsOut:
    not_implemented()


@router.delete("/image-gen", status_code=status.HTTP_204_NO_CONTENT, summary="Drop the image-gen override")
async def clear_image_gen() -> None:
    not_implemented()
