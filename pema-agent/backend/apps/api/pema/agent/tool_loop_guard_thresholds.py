# ported from: src/agent/tool-loop-guard-thresholds.ts
"""The three thresholds of ``tool_loop_guard`` and the two derivations of them.

No forced deviation. Split from ``tool_loop_guard`` because this is the NUMBER side, not the counting
side: the two functions below are pure (numbers in, numbers out), never touch the counters' state, and
both have their own traps that need a long explanation (relation to the step ceiling, floor of 2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NguongGuard:
    chan_loi_giong_het: int
    """Same tool + same parameters + failed again."""
    chan_cung_tool_loi: int
    """Same tool failing, different parameters."""
    chan_khong_tien_trien: int
    """A read tool returning the same result over and over."""


def canh_bao_tu(nguong_chan: int) -> int:
    """The warning threshold derived from the block threshold instead of 3 more config variables.

    At least 2 so that the FIRST failure is never warned about: failing once is normal, not yet a loop.
    """
    return max(2, nguong_chan // 2)


def nguong_theo_tran_step(nguong: NguongGuard, tran_step: int) -> NguongGuard:
    """Clamp the thresholds below the step ceiling, because a threshold as high as the step ceiling is a
    threshold that NEVER GETS ITS TURN.

    The three defaults (5/8/5) were carried over verbatim from Hermes' ``tool_guardrails.py``, but without
    their context: in Hermes ``max_iterations`` defaults to **90**, so 8 is only 9% of the budget. Here
    ``LLM_MAX_STEPS`` defaults to **10**, so the threshold 8 already sits below the ceiling and can fire on
    its own: the clamp no longer touches the default configuration.

    The clamp is STILL KEPT, because it targets HAND-SET configuration and not the default: lowering
    ``LLM_MAX_STEPS`` to 5 for an agent on a cheap model puts the threshold 8 out of reach at once (with
    one call per step ``stepCountIs`` always stops first, a counter reaching 8 cannot happen). Clamp here
    and not lower the default in env: someone who sets ``LLM_MAX_STEPS=30`` still gets exactly Hermes'
    three numbers. The floor of 2 so it never clamps down to 1: blocking the very first failure is
    overkill.

    The real value of the guard is that it COUNTS the failure branch that does not throw; the clamp is only
    there so the threshold is not out of reach.
    """

    def kep(n: int) -> int:
        return max(2, min(n, tran_step - 1))

    return NguongGuard(
        chan_loi_giong_het=kep(nguong.chan_loi_giong_het),
        chan_cung_tool_loi=kep(nguong.chan_cung_tool_loi),
        chan_khong_tien_trien=kep(nguong.chan_khong_tien_trien),
    )
