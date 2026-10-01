"""Zalo accounts: list, create, update, delete, QR login (package C2 implements).

Port of src/server/routes/account-routes.ts. The bot-token endpoint lives in ``admin_bot_accounts.py``
(package C1). The channel kind is fixed at creation. QR login is for ``zalo_personal`` only and goes
through the Node bridge; the README of the bridge states the account-lock risk.
"""

from __future__ import annotations

from fastapi import status

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    QrLoginStatus,
    ReactionIcon,
)

router = admin_router("accounts", "admin-accounts")


@router.get("", response_model=list[AccountOut], summary="Accounts with running state")
async def list_accounts() -> list[AccountOut]:
    not_implemented()


@router.get("/reaction-icons", response_model=list[ReactionIcon], summary="Reaction icons for auto-react")
async def list_reaction_icons() -> list[ReactionIcon]:
    not_implemented()


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, summary="Create an account")
async def create_account(body: AccountCreate) -> AccountOut:
    not_implemented()


@router.patch("/{account_id}", response_model=AccountOut, summary="Update an account")
async def update_account(account_id: str, body: AccountUpdate) -> AccountOut:
    not_implemented()


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an account and its credential"
)
async def delete_account(account_id: str) -> None:
    not_implemented()


@router.post(
    "/{account_id}/login",
    response_model=QrLoginStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start QR login (personal account)",
)
async def start_qr_login(account_id: str) -> QrLoginStatus:
    not_implemented()


@router.get("/{account_id}/login/status", response_model=QrLoginStatus, summary="Poll the QR login state")
async def get_qr_login_status(account_id: str) -> QrLoginStatus:
    not_implemented()
