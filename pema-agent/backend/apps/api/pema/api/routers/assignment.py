"""Who holds a conversation: claim, takeover, release, assign, history, end of shift (package O, step O2).

Thin routes over ``pema.clinic.actions.assignment``. Every state-changing route answers the conversation as
the
Inbox reads it (with the holder, ``assignment_version`` and the viewers), so the screen updates from the
response. A thread somebody else holds answers 409 ``thread_locked`` ("<Tên> đang trả lời — Tiếp quản?");
``details`` carries the holder id and the ``assignment_version`` to take over from.

``POST /conversations/{id}/release`` with ``to_agent`` needs package M's control state machine behind a
``CareHandback`` (``app.state.care_handback``). Until M7 wires the care loop there is none and the call
answers 501 ``not_implemented``; a release to the queue never needs it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Security

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.api.live_access import LiveDep, with_viewers
from pema.clinic.actions import assignment
from pema.clinic.actions.assignment import CareHandback
from pema_contracts.conversations import ConversationOut
from pema_contracts.ops import (
    AssignmentEventOut,
    AssignRequest,
    ClaimRequest,
    EndShiftResult,
    ReleaseRequest,
    TakeoverRequest,
)

router = APIRouter(tags=["assignment"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])


def get_care_handback(request: Request) -> CareHandback | None:
    handback: object = getattr(request.app.state, "care_handback", None)
    return handback if isinstance(handback, CareHandback) else None


CareDep = Annotated[CareHandback | None, Depends(get_care_handback)]


@router.post(
    "/conversations/{conversation_id}/claim",
    response_model=ConversationOut,
    summary="Take an unassigned conversation (Nhận)",
    description=(
        "Every operator (owner, manager, doctor, cs_staff). Only an unassigned conversation: one that a "
        "colleague holds answers 409 `thread_locked`. Claiming what you already hold changes nothing. The "
        "body is optional (`assignment_version` the client saw)."
    ),
)
async def claim_conversation(
    conversation_id: UUID, db: Database, ctx: Ctx, live: LiveDep, body: ClaimRequest | None = None
) -> ConversationOut:
    conversation = await assignment.claim(db, ctx, conversation_id, body)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.post(
    "/conversations/{conversation_id}/takeover",
    response_model=ConversationOut,
    summary="Take the conversation from the colleague who holds it (Tiếp quản)",
    description=(
        "Needs a `reason` (kept in the history, staff only). The previous holder, the new holder and the "
        "team group get a notice. 409 `invalid_state` when nobody holds it (claim it) or you already do."
    ),
)
async def takeover_conversation(
    conversation_id: UUID, body: TakeoverRequest, db: Database, ctx: Ctx, live: LiveDep
) -> ConversationOut:
    conversation = await assignment.takeover(db, ctx, conversation_id, body)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.post(
    "/conversations/{conversation_id}/release",
    response_model=ConversationOut,
    summary="Give the conversation back: to the queue, or to the care agent",
    description=(
        "The holder (or an owner or manager) puts it back in the queue. With `to_agent` the patient must be "
        "in the STAFF state of the care agent: 409 `invalid_state` otherwise, 501 until the care loop is "
        "wired. A refusal of the care agent leaves the conversation as it was."
    ),
)
async def release_conversation(
    conversation_id: UUID,
    db: Database,
    ctx: Ctx,
    live: LiveDep,
    care: CareDep,
    body: ReleaseRequest | None = None,
) -> ConversationOut:
    conversation = await assignment.release(db, ctx, conversation_id, body, care=care)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.post(
    "/conversations/{conversation_id}/assign",
    response_model=ConversationOut,
    summary="Put a colleague on the conversation (owner, manager)",
    description="`user_id` null takes it off the holder and puts it back in the queue.",
)
async def assign_conversation(
    conversation_id: UUID, body: AssignRequest, db: Database, ctx: Ctx, live: LiveDep
) -> ConversationOut:
    conversation = await assignment.assign(db, ctx, conversation_id, body)
    return (await with_viewers(db, ctx, live, [conversation]))[0]


@router.get(
    "/conversations/{conversation_id}/assignments",
    response_model=list[AssignmentEventOut],
    summary="Who held the conversation, newest first",
)
async def list_assignments(conversation_id: UUID, db: Database, ctx: Ctx) -> list[AssignmentEventOut]:
    return await assignment.list_assignments(db, ctx, conversation_id)


@router.post(
    "/staff/{user_id}/end-shift",
    response_model=EndShiftResult,
    summary="End an operator's shift: their active conversations move on (owner, manager)",
    description=(
        "Each active conversation of the user goes to an operator who is on duty for its identity (the one "
        "with the fewest active conversations), else back to the queue. A conversation that changed hands in "
        "the meantime is skipped."
    ),
)
async def end_shift(user_id: UUID, db: Database, ctx: Ctx) -> EndShiftResult:
    return await assignment.end_shift(db, ctx, user_id)
