"""Liveness probe. The only skeleton endpoint with real behaviour."""

from __future__ import annotations

from fastapi import APIRouter

from pema_contracts import __version__
from pema_contracts.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
