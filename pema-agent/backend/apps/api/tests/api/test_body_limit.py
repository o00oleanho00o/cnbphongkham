"""The body ceiling in front of every route (package G, SECURITY-REVIEW-AI01 SEC-17; no zalo-agent original)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI, Request

from pema.api.body_limit import BodyLimitMiddleware


def _app(limit: int) -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, Any]:
        return {"size": len(await request.body())}

    @app.post("/api/v1/admin/kb/sources/file")
    async def upload(request: Request) -> dict[str, Any]:
        return {"size": len(await request.body())}

    app.add_middleware(BodyLimitMiddleware, max_bytes=limit)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_a_body_within_the_ceiling_passes() -> None:
    """thân yêu cầu trong trần thì đi qua"""
    async with _client(_app(100)) as client:
        response = await client.post("/echo", content=b"x" * 100)
    assert response.status_code == 200
    assert response.json() == {"size": 100}


async def test_a_declared_length_over_the_ceiling_is_refused_with_413_before_any_read() -> None:
    """Content-Length vượt trần: 413 ngay"""
    async with _client(_app(100)) as client:
        response = await client.post("/echo", content=b"x" * 101)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_a_chunked_body_over_the_ceiling_is_cut_while_it_streams() -> None:
    """thân gửi theo từng khúc không khai độ dài cũng bị cắt khi vượt trần"""

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"y" * 30

    async with _client(_app(100)) as client:
        response = await client.post("/echo", content=chunks())
    assert response.status_code == 413


async def test_the_knowledge_base_upload_keeps_its_own_larger_limit() -> None:
    """route tải file Kho tri thức có trần riêng, không bị cắt ở đây"""
    async with _client(_app(100)) as client:
        response = await client.post("/api/v1/admin/kb/sources/file", content=b"z" * 5000)
    assert response.status_code == 200
    assert response.json() == {"size": 5000}
