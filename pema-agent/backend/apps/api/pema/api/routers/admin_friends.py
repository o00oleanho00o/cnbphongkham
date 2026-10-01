"""Friend requests and friends of a personal account (package C2).

Port of src/server/routes/friend-routes.ts.
"""

from __future__ import annotations

from pema.api.deps import admin_router, not_implemented
from pema_contracts.admin_agent import FriendDecision, FriendOut, FriendRequestOut

router = admin_router("friends", "admin-accounts")


@router.get(
    "/{account_id}/requests",
    response_model=list[FriendRequestOut],
    summary="Pending incoming friend requests",
)
async def list_friend_requests(account_id: str) -> list[FriendRequestOut]:
    not_implemented()


@router.get("/{account_id}/list", response_model=list[FriendOut], summary="Friends of the account")
async def list_friends(account_id: str) -> list[FriendOut]:
    not_implemented()


@router.post("/{account_id}/accept", summary="Accept a friend request")
async def accept_friend(account_id: str, body: FriendDecision) -> None:
    not_implemented()


@router.post("/{account_id}/reject", summary="Reject a friend request")
async def reject_friend(account_id: str, body: FriendDecision) -> None:
    not_implemented()
