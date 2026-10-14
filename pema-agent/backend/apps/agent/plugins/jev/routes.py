"""The admin routes of the jev plugin, under ``/v1/plugins/jev``: the settings (the key is only ever written),
a connection test and the usage of the last days."""

from __future__ import annotations

import time
from typing import Any, Final, Self

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_app.plugins import JudgeUnavailableError, PluginError

from .plugin import MAX_DAILY_TOKENS, USD_PER_INPUT_TOKEN, JevPlugin

NO_SEALING_KEY: Final = "Agent chưa có khóa bí mật để mã hóa (chạy bằng agent serve)."
TEST_TIMEOUT_S: Final = 15.0
TEST_STATE: Final = {"text": "Bảng giá: điều trị nám bằng laser 1.500.000đ một buổi."}
TEST_QUESTIONS: Final = {
    "states_a_price": {"type": "noul", "instructions": "Does the text state a price?"},
}


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    daily_token_cap: int | None = Field(default=None, ge=0, le=MAX_DAILY_TOKENS)
    api_key: str | None = Field(default=None, max_length=500)
    """Replaces the stored key; an empty string removes it."""

    @model_validator(mode="after")
    def _key_length(self) -> Self:
        key = (self.api_key or "").strip()
        if self.api_key is not None and key and len(key) < 8:
            raise ValueError("Khóa TypeSafe dài từ 8 đến 500 ký tự.")
        return self


def jev_routes(plugin: JevPlugin) -> APIRouter:
    router = APIRouter()

    async def shown() -> dict[str, Any]:
        settings = await plugin.settings()
        return {
            "model": settings.model,
            "daily_token_cap": settings.daily_token_cap,
            "has_key": await plugin.has_key(),
            "usd_per_million_tokens": round(USD_PER_INPUT_TOKEN * 1_000_000, 6),
        }

    @router.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return await shown()

    @router.patch("/settings")
    async def patch_settings(body: SettingsBody) -> dict[str, Any]:
        try:
            await plugin.save_settings(
                model=body.model, daily_token_cap=body.daily_token_cap, api_key=body.api_key
            )
        except PluginError as err:
            raise HTTPException(status.HTTP_409_CONFLICT, NO_SEALING_KEY) from err
        return await shown()

    @router.post("/test")
    async def test_connection() -> dict[str, Any]:
        started = time.perf_counter()
        try:
            answers = await plugin.judge([TEST_STATE], TEST_QUESTIONS, timeout_s=TEST_TIMEOUT_S)
        except JudgeUnavailableError as err:
            return {"ok": False, "ms": None, "message": err.message}
        chance = float(answers[0]["states_a_price"]["noul"])
        return {
            "ok": True,
            "ms": round((time.perf_counter() - started) * 1000),
            "message": f"Kết nối tốt (câu thử: khả năng có giá {chance:.2f}).",
        }

    @router.get("/usage")
    async def get_usage() -> dict[str, Any]:
        settings = await plugin.settings()
        today = await plugin.today()
        return {
            "daily_token_cap": settings.daily_token_cap,
            "used_today": today.tokens,
            "days": await plugin.usage(),
        }

    return router
