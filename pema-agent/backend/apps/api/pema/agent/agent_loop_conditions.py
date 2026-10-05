# ported from: src/agent/agent-loop-conditions.ts
"""PURE predicates deciding when the agent loop stops and how a turn ends.

Forced deviation (Vercel AI SDK -> own loop): ``vuot_tran_token`` returns a predicate over the list of
``RawStep`` instead of the SDK's ``({ steps }) => boolean`` object argument; the loop calls it after every
step as the ``stopWhen`` condition.

Split from ``agent_loop`` because this is the only part of the loop that can be tested without a model, a
DB or a network: gathered in one place it is obvious what is pure logic and what has to run for real.

NOT meant to bring ``agent_loop`` under 200 lines: that file is still several times the threshold. The rest
of it is one continuous loop with failure-tolerant branches woven together, cutting further would only make
it harder to read.

``agent_loop`` re-exports these so every place imports as before.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pema.agent.model_types import RawStep


def is_empty_router_completion(*, text: str, tool_call_count: int, total_tokens: int) -> bool:
    """Signature of "the router returned an empty completion": 9Router occasionally returns HTTP 200 with a
    blank message - no text, no tool call, usage = 0. The SDK treats that as success so ``maxRetries`` does
    not save us. Distinguishable from a legitimate "only dropped a reaction" turn: that turn HAS a tool call
    and HAS tokens."""
    return not text.strip() and tool_call_count == 0 and total_tokens == 0


def hit_step_limit(*, step_count: int, max_steps: int, last_step_tool_calls: int) -> bool:
    """The turn stopped because it RAN OUT OF TOOL CALLS and not because the model finished.

    Recognised by STRUCTURE (enough steps + the last step still calls tools) instead of by
    ``finishReason``: a model that is done has no tool call in its last step, whereas ``stopWhen:
    stepCountIs(n)`` cuts exactly when the model has just called a tool. ``finishReason`` is not used
    because that field is mapped by the provider, and the SDK's ``MockLanguageModel`` does not pass it out
    so this branch could not be tested.

    Now only used to WRITE THE LOG of why it stopped. Whether to run the wrap-up turn belongs to
    ``can_luot_chot`` - see the explanation there.
    """
    return step_count >= max_steps and last_step_tool_calls > 0


def can_luot_chot(*, last_step_tool_calls: int) -> bool:
    """Does the turn need a WRAP-UP TURN: more general than ``hit_step_limit``.

    The deciding sign is THE LAST STEP STILL CALLING A TOOL. A model that is done has no tool call in its
    last step; still calling means the loop was cut off midway, so ``result.text`` is a progress narration
    ("2 sources enough - now cross-check") and not the answer.

    Why not use ``hit_step_limit`` directly: that function also demands ``step_count >= max_steps``, which
    is right when running out of steps is the ONLY reason to stop. Since ``stopWhen`` got a token condition
    (``vuot_tran_token``), a turn stopping early with ``len(steps) < max_steps`` slips off that branch and
    sends the narration straight down to Zalo - the very bug the wrap-up turn was created to cure.
    """
    return last_step_tool_calls > 0


def vuot_tran_token(tran_token: float) -> Callable[[Sequence[RawStep]], bool]:
    """Stop condition by TOKENS, combined with ``stepCountIs`` in ``stopWhen``.

    Based on the REAL usage the provider returns after every step, not on an estimate: the estimate is only
    used to cut context BEFORE the turn, inside the turn there is a real number to trust.

    ``steps[].usage.input_tokens`` is the input of THAT step alone (measured with ``MockLanguageModelV4`` on
    ``ai@7.0.37``: a mock returning 1000/3000/7000 reads back exactly those three numbers, while
    ``totalUsage`` is 11000). Take the max rather than the sum: what decides whether the window overflows
    is the HEAVIEST call, the sum only says how much money was spent.

    What is passed in must be the BUDGET with the safety margin applied (``ngan_sach_an_toan``), not the raw
    ceiling: ``usage`` only comes back after that call SUCCEEDED, so against the raw ceiling the provider
    would already have answered 400 before this function ever saw the number that went over.
    """

    def kiem_tra(steps: Sequence[RawStep]) -> bool:
        if tran_token <= 0:
            return False
        nang_nhat = 0
        for s in steps:
            nang_nhat = max(nang_nhat, (s.usage.input_tokens or 0) if s.usage is not None else 0)
        return nang_nhat >= tran_token

    return kiem_tra


def nhan_ly_do_dung(*, ma_guard_chan: str | None = None, het_step: bool) -> str:
    """Label for WHY the loop stopped, for the log line people read to understand why a turn was cut short.

    A pure function because the previous version wrote it straight in the log and wrote it BINARY from when
    there were only two stop conditions (``out of steps`` : ``token ceiling reached``). The guard added later
    became the third condition, so every time the guard blocked it was logged wrongly as the token ceiling:
    a wrong diagnosis at the very first clue. Here that kind of mismatch is checkable with a test, no log
    capture needed.

    The guard is considered FIRST: when the guard blocks, the loop stopped because of the guard, even if the
    step count happened to hit the ceiling too.
    """
    if ma_guard_chan:
        return f"guard chặn ({ma_guard_chan})"
    return "hết step" if het_step else "chạm trần token"
