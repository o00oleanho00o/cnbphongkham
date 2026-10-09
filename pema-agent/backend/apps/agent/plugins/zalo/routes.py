# ported from: src/server/routes/account-routes.ts
"""Admin routes of the Zalo plugin, under ``/v1/plugins/zalo`` (admin token): list, create, change and delete
accounts, and the reaction icons the dashboard offers for auto-react.

The kind of an account is fixed at creation (delete and create again to change it). Request and response
shapes follow the earlier admin API so the dashboard pages carry over.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response, status

from .accounts import AccountExistsError, AccountStore
from .models import AccountConfig, AccountCreate, AccountOut, AccountUpdate, ReactionIconOut
from .reaction_icons import REACTION_ICONS


def account_routes(store: AccountStore, *, running: Callable[[str], bool]) -> APIRouter:
    router = APIRouter()

    async def out(account: AccountConfig, warning: str | None = None) -> AccountOut:
        return AccountOut.model_validate(
            {
                **account.model_dump(),
                "running": running(account.id),
                "has_credentials": await store.has_secret(account.id),
                "warning": warning,
            }
        )

    @router.get("/accounts")
    async def list_accounts() -> list[AccountOut]:
        return [await out(account) for account in await store.list()]

    # Before ``/accounts/{account_id}``-style routes so the path is not read as an account id.
    @router.get("/accounts/reaction-icons")
    async def list_reaction_icons() -> list[ReactionIconOut]:
        return [
            ReactionIconOut(key=key, emoji=icon.emoji, label=icon.label)
            for key, icon in REACTION_ICONS.items()
        ]

    @router.post("/accounts", status_code=status.HTTP_201_CREATED)
    async def create_account(body: AccountCreate) -> AccountOut:
        try:
            created = await store.create(body)
        except AccountExistsError as err:
            raise HTTPException(status.HTTP_409_CONFLICT, "Account id đã tồn tại") from err
        return await out(created)

    @router.patch("/accounts/{account_id}")
    async def update_account(account_id: str, body: AccountUpdate) -> AccountOut:
        if body.auto_react_icon is not None and body.auto_react_icon not in REACTION_ICONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Icon reaction không hợp lệ")
        try:
            updated = await store.update(account_id, body)
        except ValueError as err:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Cấu hình tài khoản không hợp lệ"
            ) from err
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        return await out(updated)

    @router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_account(account_id: str) -> Response:
        if not await store.delete(account_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
