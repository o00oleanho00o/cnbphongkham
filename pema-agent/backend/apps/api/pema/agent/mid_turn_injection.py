# ported from: src/agent/mid-turn-injection.ts
"""Inject the messages a user sent WHILE an agent turn is running, into that turn.

The problem left after the batcher learned to merge messages (``message-batcher.ts``): the first turn still
launches with partial context. Real case 2026-08-04: the user answered one sentence, the bot started building
a document, 50 seconds later the user sent two more sentences clarifying the request. Merging only lowered 3
turns to 2; the first turn still finished a whole 18,000-character document on a request that was not
complete.

The insertion point is the STEP BOUNDARY: after the tool results, before the next LLM call, the place goclaw
uses (``internal/pipeline/observe_stage.go`` consumes ``InjectCh``). In the loop this is ``prepare_step``
(``stream_text_result``); the overriding message list is carried forward to later steps so inserting once is
enough. The Anthropic path is safe: its adapter merges a ``tool`` message and the following ``user`` message
into ONE ``user`` block, so a user message right after a tool result never breaks "roles must alternate".

Forced deviation: ``ParsedMessage`` is ``InboundMessage``; ``prepareStep`` returning ``{messages}`` or ``{}``
becomes returning the new list or ``None`` (no change); the content builder takes its injected collaborators.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from pema.agent.agent_turn_content import ImageContextMode, TurnContentDeps, build_current_turn_content
from pema.agent.model_types import ModelMessage
from pema.agent.token_estimate import TOKEN_MOI_ANH_THEO_CO, ngan_sach_an_toan, uoc_luong_token_tin_nhan
from pema.config.runtime_tuning_settings import get_tuning, get_tuning_bool
from pema.shared.logger import create_logger
from pema_contracts.channel import InboundMessage

# Same scope as ``agent-loop`` and not a scope of its own: reading the log of a failed turn is reading the
# timeline of that turn, a separate scope only forces joining by hand. ``agent_step_observer`` does the same.
log = create_logger("agent-loop")

NHAN_TIN_CHEN = (
    "[Vừa có tin nhắn mới trong cuộc trò chuyện này trong lúc bạn đang làm dở. "
    "Tên người gửi ghi ngay dưới đây. Tính nội dung đó vào việc đang làm: nếu nó "
    "đổi yêu cầu thì đổi theo, nếu chỉ bổ sung thì làm tiếp cho trọn. Đừng bắt "
    "đầu lại từ đầu, và đừng làm lại thứ đã xong.]"
)
"""The label put before the content of an injected message.

NOT wrapped in ``<noi_dung_ngoai>`` like web content: this is a real person's words in the conversation, the
same trust as the opening message of the turn (it passed the allowlist at ``shouldRespond``). Wrapping it as
external data would teach the model to ignore exactly the person it must listen to. The injected message is
now SURE to come from the same person as the opening one (the fetch is per ``(thread, sender)``), and the
label keeps the old vague wording even though it could now be explicit: ``build_current_turn_content`` already
pastes the name and send time of EACH message right below, so another identity claim in the label is
superfluous and one more place to fix if the scope of the fetch changes again.

It says plainly "đang làm dở" because without that sentence the model easily reads the injected message as a
completely NEW request and drops the work in progress."""

TY_LE_TRAN_TIN_CHEN = 0.25
"""The share of the token budget an injected message may take.

``messages`` was already cut to the budget at ``build_turn_messages``, and the injected message is added
DIRECTLY, through no cutter. A few words are harmless, but the fetch returns up to 32 messages and each may
carry several images: in ``native`` mode every image is a full base64 block. Someone sending 8 pictures while
the bot runs is enough to push an already near-ceiling context over.

Not relying on the self-repair path (``context_overflow`` cuts deeper and retries): it costs a whole model
call,
and that call fails anyway."""


async def dung_tin_chen(
    tin_moi: Sequence[InboundMessage], image_mode: ImageContextMode, *, deps: TurnContentDeps
) -> ModelMessage:
    """Build the injected messages into ONE ``user`` ``ModelMessage``.

    Reuses ``build_current_turn_content`` instead of gluing strings: it already handles images per the running
    mode (native/describe/hybrid/blind), the sender label in a group, and the "image without text" case. A
    second path here would surely drift from the first, and this one is the one less often looked at.
    """
    noi_dung = await build_current_turn_content(tin_moi, image_mode, deps=deps)
    nhan = {"type": "text", "text": NHAN_TIN_CHEN}
    return {"role": "user", "content": [nhan, *noi_dung]}


async def dung_tin_chen_trong_ngan_sach(
    moi: Sequence[InboundMessage], image_mode: ImageContextMode, tran_token: int, *, deps: TurnContentDeps
) -> ModelMessage:
    """Build the injected message and, if it is too big, rebuild it WITHOUT images.

    Drop the images, keep the text, not the whole message: the text is what changes the request, the images
    stay in the history so the next turn can read them again.
    """
    tin_chen = await dung_tin_chen(moi, image_mode, deps=deps)
    co_anh = str(get_tuning("ZALO_IMAGE_QUALITY"))
    token_moi_anh = {**TOKEN_MOI_ANH_THEO_CO}.get(co_anh, TOKEN_MOI_ANH_THEO_CO["normal"])
    uoc_luong = uoc_luong_token_tin_nhan([tin_chen], token_moi_anh)
    tran = int(ngan_sach_an_toan(tran_token) * TY_LE_TRAN_TIN_CHEN)
    if tran <= 0 or uoc_luong <= tran:
        return tin_chen

    log.warning(
        "injected message too large for the budget: rebuilt WITHOUT images so the context does not overflow",
        uoc_luong=uoc_luong,
        tran=tran,
        so_tin=len(moi),
    )
    return await dung_tin_chen(moi, "blind", deps=deps)


class _HasDatLai(Protocol):
    def dat_lai(self) -> None: ...


def tao_bo_chen_tin(
    *,
    lay_tin_chen: Callable[[], Awaitable[Sequence[InboundMessage]]] | None,
    lay_image_mode: Callable[[], ImageContextMode],
    lay_tran_token: Callable[[], int],
    guard: _HasDatLai,
    deps: TurnContentDeps,
) -> Callable[[list[ModelMessage]], Awaitable[list[ModelMessage] | None]]:
    """Build the function for ``prepare_step`` of the agent loop.

    The WHOLE body is in a try/except and every failing branch returns ``None`` (no change). This is the "do
    better" branch, not the mandatory one: an error here (a broken queue, an image of the injected message
    that cannot be downloaded) that is raised would kill the running turn, the one that just spent minutes
    calling tools. Better to skip the insertion than lose the answer.

    ``lay_tin_chen`` None disables the whole path (a scheduled turn passes none). ``lay_image_mode`` is a
    FUNCTION: it changes mid-turn when the provider refuses pixels and the loop rebuilds the input without
    images; passing the value would build the injected message in a mode that is no longer valid, and the turn
    that was refused over an image would receive more.
    """

    async def chen(tin_hien_tai: list[ModelMessage]) -> list[ModelMessage] | None:
        if lay_tin_chen is None or not get_tuning_bool("MID_TURN_INJECTION_ENABLED"):
            return None
        try:
            moi = list(await lay_tin_chen())
            if not moi:
                return None

            tin_chen = await dung_tin_chen_trong_ngan_sach(moi, lay_image_mode(), lay_tran_token(), deps=deps)

            # Reset the guard counters: an injected message is NEW CONTEXT, it must not carry the sins of the
            # part before it. The model was stuck on the old direction and called one tool repeatedly, and now
            # the user just changed direction: blocking it with the counter of the old direction blocks
            # exactly the new work. Same reason as the ``lan_chay += 1`` branches. No fear of running for
            # ever: the step ceiling still stops it and that ceiling is NOT reset.
            guard.dat_lai()

            log.info("injecting messages the user sent mid-turn", so_tin=len(moi))
            return [*tin_hien_tai, tin_chen]
        except Exception as err:
            log.error("mid-turn injection failed - skipped, the turn continues normally", err=err)
            return None

    return chen
