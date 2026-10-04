"""Reference sequence of a turn under a policy profile (what the agent loop must do around the model).

New module. The call sites of the eight hooks belong to other packages (D1 ``run_turn``, C2
``deliver_chat_reply``, S ``deliver_proactively``); this package does not edit them. ``run_guarded_turn``
is the SAME ordering written once, as a small function, so that

* package D1/C2 can read the contract as code (and may call it in tests of their own wiring);
* the evals and the policy tests can prove the one property that matters most, "a red-flag message never
  reaches the model", with a fake model that counts its calls.

Order (normative, from ``docs/CONTRACTS-AI01.md`` section 3):

1. ``before_llm`` on the batch. ``HAND_OFF`` stops here: the model is not called.
2. the model is called with the MASKED text (``masked_text_by_msg_id``), nothing else of the patient.
3. ``after_llm`` restores names in the reply.
4. ``on_outbound``: ``SEND`` or ``HOLD_FOR_REVIEW`` (the caller opens the review item) or ``DROP``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pema_contracts.channel import InboundMessage
from pema_contracts.policy import (
    BeforeLlmAction,
    OutboundDecision,
    OutboundOrigin,
    PolicyContext,
    PolicyHooks,
)


@dataclass(frozen=True)
class GuardedTurn:
    handed_off: bool
    hand_off_reason: str | None = None
    red_flags: list[str] = field(default_factory=list[str])
    model_input: str | None = None
    """Exactly what the model was given; ``None`` when it was not called."""
    reply: str | None = None
    outbound: OutboundDecision | None = None

    @property
    def model_called(self) -> bool:
        return self.model_input is not None


def model_input_of(batch: Sequence[InboundMessage], masked: dict[str, str]) -> str:
    return "\n".join(masked.get(m.msg_id, m.text) for m in batch if not m.is_self and m.text)


async def run_guarded_turn(
    hooks: PolicyHooks,
    ctx: PolicyContext,
    batch: Sequence[InboundMessage],
    generate: Callable[[str], Awaitable[str]],
) -> GuardedTurn:
    decision = await hooks.before_llm(ctx, batch)
    if decision.action is BeforeLlmAction.HAND_OFF:
        return GuardedTurn(
            handed_off=True, hand_off_reason=decision.reason, red_flags=list(decision.red_flags)
        )
    model_input = model_input_of(batch, decision.masked_text_by_msg_id)
    raw_reply = await generate(model_input)
    reply = await hooks.after_llm(ctx, raw_reply, decision.mask_token)
    outbound = await hooks.on_outbound(ctx, reply, proactive=False, origin=OutboundOrigin.TURN_REPLY)
    return GuardedTurn(
        handed_off=False,
        red_flags=list(decision.red_flags),
        model_input=model_input,
        reply=reply,
        outbound=outbound,
    )
