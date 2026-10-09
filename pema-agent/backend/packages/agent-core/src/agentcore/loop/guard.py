"""Notices a turn that goes round in circles: the same tool call with the same arguments again and again, or
tool call after tool call failing.

Modelled on deepseek-harness's ``repeat-tool-reminder``: consecutive identical calls (arguments compared with
their keys sorted) earn a reminder at each threshold, gentle at the first, detailed after; a different call
starts the count again and an excluded tool neither counts nor breaks the run. Here a run that goes on past
``stop_after_repeats``, or ``error_streak_stop`` failures in a row, also ends the turn's tool use. The count
lives for one turn. The reminder wording is theirs (MIT License, Copyright (c) 2026 DeepSeek).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Literal

from agentcore.messages import ToolResultBlock, ToolUseBlock

GENTLE_REMINDER: Final = (
    "You are repeating the exact same tool call with identical arguments. Carefully analyse the previous "
    "result before calling again: if the task is not complete, try a different approach or different "
    "arguments instead of repeating the call."
)
ERROR_REMINDER: Final = (
    "The last {count} tool calls failed. Read the error messages: fix the arguments, try a different tool, "
    "or answer with what you have and say what did not work."
)

GuardReason = Literal["repeat", "errors"]


@dataclass(frozen=True, slots=True)
class LoopGuardPolicy:
    repeat_thresholds: tuple[int, ...] = (3, 5, 8)
    stop_after_repeats: int | None = 10
    """Identical calls in a row after which the turn stops using tools; None only reminds."""
    error_streak_remind: int | None = 3
    error_streak_stop: int | None = 5
    exclude: tuple[str, ...] = ()
    """Tools that neither count nor break a run of identical calls."""
    preview_chars: int = 500

    def __post_init__(self) -> None:
        thresholds = self.repeat_thresholds
        if not thresholds or any(t < 2 for t in thresholds) or len(set(thresholds)) != len(thresholds):
            raise ValueError("repeat_thresholds: whole numbers of 2 or more, without duplicates")
        if self.stop_after_repeats is not None and self.stop_after_repeats <= max(thresholds):
            raise ValueError("stop_after_repeats must be above the last repeat threshold")
        remind, stop = self.error_streak_remind, self.error_streak_stop
        if (remind is not None and remind < 1) or (stop is not None and stop < 1):
            raise ValueError("error streak limits must be at least 1")
        if remind is not None and stop is not None and stop <= remind:
            raise ValueError("error_streak_stop must be above error_streak_remind")
        if self.preview_chars < 1:
            raise ValueError("preview_chars must be at least 1")

    @property
    def sorted_thresholds(self) -> tuple[int, ...]:
        return tuple(sorted(self.repeat_thresholds))


@dataclass(frozen=True, slots=True)
class GuardNote:
    reason: GuardReason
    tool: str
    count: int
    text: str
    """What the model reads in its next request; empty when the turn stops."""
    stop: bool = False


class LoopGuard:
    def __init__(self, policy: LoopGuardPolicy | None = None) -> None:
        self.policy = policy or LoopGuardPolicy()
        self._key: str | None = None
        self._repeats = 0
        self._errors = 0

    def observe(self, use: ToolUseBlock, result: ToolResultBlock) -> list[GuardNote]:
        """Counts one finished call; returns the reminders (or the stop) it triggers."""
        notes: list[GuardNote] = []
        policy = self.policy
        if use.name not in policy.exclude:
            canonical = canonical_arguments(use)
            key = f"{use.name}\x00{canonical}"
            self._repeats = self._repeats + 1 if key == self._key else 1
            self._key = key
            if policy.stop_after_repeats is not None and self._repeats >= policy.stop_after_repeats:
                notes.append(GuardNote("repeat", use.name, self._repeats, "", stop=True))
            elif self._repeats in policy.repeat_thresholds:
                text = (
                    GENTLE_REMINDER
                    if self._repeats == policy.sorted_thresholds[0]
                    else _detailed(use.name, self._repeats, canonical, policy.preview_chars)
                )
                notes.append(GuardNote("repeat", use.name, self._repeats, text))
        self._errors = self._errors + 1 if result.is_error else 0
        if policy.error_streak_stop is not None and self._errors >= policy.error_streak_stop:
            notes.append(GuardNote("errors", use.name, self._errors, "", stop=True))
        elif policy.error_streak_remind is not None and self._errors == policy.error_streak_remind:
            notes.append(
                GuardNote("errors", use.name, self._errors, ERROR_REMINDER.format(count=self._errors))
            )
        return notes


def canonical_arguments(use: ToolUseBlock) -> str:
    """The arguments with their keys sorted, so a different key order is the same call; the raw text when the
    model sent no JSON object."""
    if use.raw_args is not None and not use.args:
        return use.raw_args
    return json.dumps(use.args, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _detailed(tool: str, count: int, canonical: str, cap: int) -> str:
    shown = canonical if len(canonical) <= cap else f"{canonical[:cap]}… (+{len(canonical) - cap} more chars)"
    return (
        "Repeated tool call detected:\n"
        f"- tool: {tool}\n"
        f"- consecutive_calls: {count}\n"
        f"- arguments: {shown}\n"
        "The repeated calls are not making progress. Do not call this tool with these exact arguments again. "
        "Inspect the latest result and choose a different action, different arguments, or finish the task if "
        "enough evidence has been gathered."
    )
