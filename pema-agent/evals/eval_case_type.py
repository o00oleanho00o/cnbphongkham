# ported from: evals/eval-case-type.ts
"""Shape of one eval case.

It differs from ``pytest`` at the root: the tests run a FAKE model and so measure what is deterministic
(wiring, error branches, order). This suite runs a REAL model and so measures what a test cannot: does the
model look things up instead of guessing, does it ask back when information is missing, does it get worse
after the persona was edited.

Pure module: it only declares types.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from evals.eval_formatting_view import DinhDangDaGui


@dataclass(frozen=True)
class KiemTraText:
    """Assertion on the bare reply text.

    ONLY for STRUCTURAL properties: ends with a question mark, has no ``**``, shorter than N. Asserting
    SEMANTIC content ("must contain the word X") is FORBIDDEN: the model varies between runs, so wording is a
    source of random red, and a randomly red eval is one people stop reading, which loses the real reds too.
    """

    mo_ta: str
    dat: Callable[[str], bool]


@dataclass(frozen=True)
class KiemTraDinhDang:
    """Assertion on the formatting that really reached Zalo, not on the text.

    ``kiem_tra_text`` receives the BARE text after the markdown was translated, when the ``**`` markers have
    disappeared, so there is no way to know whether anything was bold. That gap made every presentation fault
    something the user had to discover; see ``eval_formatting_view``.
    """

    mo_ta: str
    dat: Callable[[DinhDangDaGui], bool]


@dataclass(frozen=True)
class KiemTraToolArgs:
    """Assertion on the ARGUMENTS the model passed to a tool, not only its name.

    Needed by cases where calling the right tool can still be entirely wrong: ``save_memory`` with ``action:
    "them"`` right after the user corrected something ADDS a contradiction, while a measurement that only
    looks at the tool name reports green. ``input`` is the JSON string exactly as the trace recorded it.
    """

    tool: str
    mo_ta: str
    dat: Callable[[str], bool]


@dataclass(frozen=True)
class MongDoi:
    goi_tool: list[str] = field(default_factory=list[str])
    """MUST be called (any order, calling other tools too is fine)."""
    khong_goi_tool: list[str] = field(default_factory=list[str])
    """MUST NOT be called, ever."""
    goi_tool_it_nhat: dict[str, int] = field(default_factory=dict[str, int])
    """MINIMUM number of calls of a tool.

    ``goi_tool`` compares sets, so it only answers "was it called". It cannot tell READING ONE ARTICLE from
    READING THREE, which is exactly the difference between a digest with its own source per item and one with
    a single shared source line at the end. Measured on real Zalo: the model opened exactly one article and
    stopped, because the old rule only asked for "at least one".
    """
    kiem_tra_text: KiemTraText | None = None
    kiem_tra_dinh_dang: KiemTraDinhDang | None = None
    kiem_tra_tool_args: KiemTraToolArgs | None = None


@dataclass(frozen=True)
class LichSuTin:
    """One pre-built history row."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class EvalCase:
    ten: str
    ly_do: str
    """WHY this case exists. Mandatory, not decoration: a case that cannot say why it exists is one the next
    person deletes by mistake when it goes red, or worse, edits the expectation until it is green without
    knowing a barrier was just lost."""
    tin_nhan: str
    """What the user writes."""
    mong_doi: MongDoi
    persona: str = ""
    """Persona of this case; empty means the empty persona (only BASE_PERSONA applies)."""
    disabled_tools: list[str] = field(default_factory=list[str])
    """Tools turned OFF for this case's agent: tries the "narrow agent" branch."""
    lich_su_truoc: list[LichSuTin] = field(default_factory=list[LichSuTin])
    """History BUILT before ``tin_nhan`` is sent.

    WHY - a gap paid for on 2026-08-05: the eval ran on a BLANK thread while the real bot always has history.
    A model imitates the formatting of ITS OWN previous turn very strongly, so after a persona rule change the
    eval was green (blank thread) while the user still saw the old style (thread with history). Measured: same
    system prompt, blank thread 2/2 times numbered by the new rule, a thread with an old flat reply 2/2 times
    copied the old style.
    """
    la_nhom: bool = False
    """Group chat instead of a private one."""
    fact_co_san: list[str] = field(default_factory=list[str])
    """What the bot ALREADY remembers about the sender, seeded before the turn. Without it the edit/delete
    branch of ``save_memory`` cannot be measured: the model must be remembering something WRONG for the
    correction to mean anything."""
